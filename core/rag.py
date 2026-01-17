"""RAG Pipeline с векторными эмбеддингами для юридических документов.

Использует ChromaDB для хранения и поиска эмбеддингов.
Поддерживает fallback на keyword matching если ChromaDB недоступен.
Включает систему непрерывного обучения на новых договорах.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Опциональные зависимости для векторного поиска
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Using keyword matching fallback.")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning("sentence-transformers not installed. Using keyword matching.")


@dataclass
class Document:
    """Документ для RAG с метаданными."""

    content: str
    metadata: dict[str, Any]
    score: float = 0.0


@dataclass
class LearningRecord:
    """Запись об обучении системы на документе."""

    document_hash: str
    document_type: str
    added_at: str
    source: str  # email, manual, template
    parties: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


class SimpleRAG:
    """RAG система с векторными эмбеддингами (ChromaDB).

    Возможности:
    - Векторный поиск через ChromaDB + sentence-transformers
    - Fallback на keyword matching если библиотеки недоступны
    - Pre-Retrieval: расширение запроса синонимами
    - Post-Retrieval: переранжирование и фильтрация
    """

    # Юридические синонимы для Pre-Retrieval
    LEGAL_SYNONYMS = {
        'договор': ['контракт', 'соглашение', 'сделка'],
        'исполнитель': ['подрядчик', 'поставщик', 'продавец'],
        'заказчик': ['покупатель', 'клиент', 'заказывающая сторона'],
        'аренда': ['наём', 'найм', 'съём'],
        'оплата': ['платёж', 'расчёт', 'вознаграждение'],
        'срок': ['период', 'дата', 'время'],
        'сумма': ['стоимость', 'цена', 'размер'],
        'стороны': ['участники', 'контрагенты'],
        'обязательство': ['обязанность', 'долг', 'ответственность'],
        'товар': ['продукция', 'изделие', 'материал'],
        'услуга': ['работа', 'сервис', 'обслуживание'],
    }

    # Ключевые слова для определения договора
    CONTRACT_KEYWORDS = [
        'договор', 'контракт', 'соглашение', 'стороны',
        'исполнитель', 'заказчик', 'обязуется', 'предмет договора',
        'срок действия', 'порядок расчётов', 'реквизиты',
        'ответственность сторон', 'расторжение', 'подпись'
    ]

    # Модель для эмбеддингов (мультиязычная, поддерживает русский)
    EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(
        self,
        templates_dir: str = "templates",
        persist_dir: str = ".chroma_db",
        use_gpu: bool = False,
        enable_learning: bool = True,
        learning_history_file: str = ".rag_learning_history.json"
    ):
        """Инициализация RAG системы.

        Args:
            templates_dir: Директория с шаблонами договоров
            persist_dir: Директория для хранения ChromaDB
            use_gpu: Использовать GPU для эмбеддингов
            enable_learning: Включить автоматическое обучение на новых документах
            learning_history_file: Файл для хранения истории обучения
        """
        self.templates_dir = Path(templates_dir)
        self.persist_dir = Path(persist_dir)
        self.documents: list[Document] = []

        # Настройки обучения
        self.enable_learning = enable_learning
        self.learning_history_file = Path(persist_dir) / learning_history_file
        self.learning_history: list[LearningRecord] = []
        self.learned_hashes: set = set()  # Для быстрой проверки дубликатов

        # Инициализация векторного поиска
        self.use_vector_search = CHROMADB_AVAILABLE and EMBEDDINGS_AVAILABLE
        self.embedder = None
        self.chroma_client = None
        self.collection = None

        if self.use_vector_search:
            self._init_vector_store(use_gpu)
        else:
            logger.info("Using keyword matching (install chromadb, "
                        "sentence-transformers for vector search)")

        self._load_templates()
        self._load_learning_history()

    def _init_vector_store(self, use_gpu: bool = False):
        """Инициализация ChromaDB и модели эмбеддингов."""
        try:
            # Инициализация модели эмбеддингов
            device = "cuda" if use_gpu else "cpu"
            self.embedder = SentenceTransformer(self.EMBEDDING_MODEL, device=device)
            logger.info(f"Loaded embedding model: {self.EMBEDDING_MODEL} on {device}")

            # Инициализация ChromaDB (новый API)
            self.persist_dir.mkdir(exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )

            # Создаём или получаем коллекцию
            self.collection = self.chroma_client.get_or_create_collection(
                name="legal_documents",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB initialized: {self.collection.count()} documents")

        except Exception as e:
            logger.error(f"Failed to init vector store: {e}")
            self.use_vector_search = False

    def _load_templates(self):
        """Загрузка шаблонов договоров из директории."""
        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}")
            return

        loaded = 0
        new_docs_for_indexing = []

        for file_path in self.templates_dir.glob("*.docx"):
            try:
                content = self._read_docx(file_path)
                if content:
                    doc = Document(
                        content=content,
                        metadata={
                            'filename': file_path.name,
                            'path': str(file_path),
                            'type': 'template'
                        }
                    )
                    self.documents.append(doc)
                    new_docs_for_indexing.append(doc)
                    loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        # Индексируем новые документы в ChromaDB
        if self.use_vector_search and new_docs_for_indexing:
            self._index_documents(new_docs_for_indexing)

        logger.info(f"Loaded {loaded} contract templates from {self.templates_dir}")

    def _index_documents(self, documents: list[Document]):
        """Индексация документов в ChromaDB."""
        if not self.use_vector_search or not documents:
            return

        try:
            # Подготовка данных для ChromaDB
            texts = [doc.content[:5000] for doc in documents]  # Ограничиваем размер
            ids = [f"doc_{hash(doc.metadata['path'])}" for doc in documents]
            metadatas = [doc.metadata for doc in documents]

            # Генерация эмбеддингов
            embeddings = self.embedder.encode(texts, show_progress_bar=False)

            # Добавление в коллекцию
            self.collection.add(
                embeddings=embeddings.tolist(),
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Indexed {len(documents)} documents in ChromaDB")

        except Exception as e:
            logger.error(f"Failed to index documents: {e}")

    def _read_docx(self, file_path: Path) -> str:
        """Чтение DOCX файла"""
        try:
            import docx2txt
            return docx2txt.process(str(file_path))
        except ImportError:
            logger.error("docx2txt not installed. Run: pip install docx2txt")
            return ""
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return ""

    # ========== LEARNING SYSTEM ==========

    def _load_learning_history(self):
        """Загрузка истории обучения из файла."""
        if not self.learning_history_file.exists():
            logger.info("No learning history found, starting fresh")
            return

        try:
            with open(self.learning_history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for record in data.get('records', []):
                lr = LearningRecord(
                    document_hash=record['document_hash'],
                    document_type=record.get('document_type', 'unknown'),
                    added_at=record['added_at'],
                    source=record.get('source', 'unknown'),
                    parties=record.get('parties', []),
                    keywords=record.get('keywords', [])
                )
                self.learning_history.append(lr)
                self.learned_hashes.add(lr.document_hash)

            logger.info(f"Loaded {len(self.learning_history)} learning records")
        except Exception as e:
            logger.error(f"Failed to load learning history: {e}")

    def _save_learning_history(self):
        """Сохранение истории обучения в файл."""
        try:
            self.persist_dir.mkdir(exist_ok=True)
            data = {
                'version': '1.0',
                'last_updated': datetime.now().isoformat(),
                'total_documents': len(self.learning_history),
                'records': [
                    {
                        'document_hash': lr.document_hash,
                        'document_type': lr.document_type,
                        'added_at': lr.added_at,
                        'source': lr.source,
                        'parties': lr.parties,
                        'keywords': lr.keywords
                    }
                    for lr in self.learning_history
                ]
            }

            with open(self.learning_history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved {len(self.learning_history)} learning records")
        except Exception as e:
            logger.error(f"Failed to save learning history: {e}")

    def _compute_document_hash(self, content: str) -> str:
        """Вычисление хэша документа для дедупликации."""
        # Нормализуем текст перед хэшированием
        normalized = re.sub(r'\s+', ' ', content.lower().strip())
        # Берём первые 2000 символов для хэша (достаточно для уникальности)
        return hashlib.sha256(normalized[:2000].encode('utf-8')).hexdigest()

    def _extract_keywords_from_content(self, content: str) -> list[str]:
        """Извлечение ключевых слов из контента для метаданных."""
        content_lower = content.lower()
        found_keywords = []

        for keyword in self.CONTRACT_KEYWORDS:
            if keyword in content_lower:
                found_keywords.append(keyword)

        return found_keywords[:10]  # Ограничиваем количество

    def learn_from_document(
        self,
        content: str,
        document_type: str = "unknown",
        source: str = "manual",
        parties: list[str | None] = None,
        force: bool = False
    ) -> dict[str, Any]:
        """Обучение системы на новом документе.

        Добавляет документ в базу знаний для улучшения поиска.
        Предотвращает добавление дубликатов.

        Args:
            content: Текст документа
            document_type: Тип документа (договор аренды, поставки и т.д.)
            source: Источник документа (email, manual, template)
            parties: Стороны договора
            force: Принудительно добавить даже если похожий уже есть

        Returns:
            Результат обучения с информацией об успехе/ошибке
        """
        if not self.enable_learning:
            return {
                'success': False,
                'reason': 'learning_disabled',
                'message': 'Автоматическое обучение отключено'
            }

        if not content or len(content.strip()) < 100:
            return {
                'success': False,
                'reason': 'content_too_short',
                'message': 'Документ слишком короткий для обучения'
            }

        # Проверяем, является ли это договором
        is_contract, confidence = self.is_contract(content)
        if not is_contract and not force:
            return {
                'success': False,
                'reason': 'not_a_contract',
                'confidence': confidence,
                'message': 'Документ не похож на договор'
            }

        # Проверяем дубликаты
        doc_hash = self._compute_document_hash(content)
        if doc_hash in self.learned_hashes and not force:
            return {
                'success': False,
                'reason': 'duplicate',
                'hash': doc_hash,
                'message': 'Документ уже существует в базе знаний'
            }

        # Извлекаем ключевые слова
        keywords = self._extract_keywords_from_content(content)

        # Создаём метаданные
        metadata = {
            'type': 'learned',
            'document_type': document_type,
            'source': source,
            'parties': parties or [],
            'keywords': keywords,
            'added_at': datetime.now().isoformat(),
            'hash': doc_hash,
            'content_length': len(content)
        }

        # Добавляем в индекс
        doc = Document(content=content, metadata=metadata)
        self.documents.append(doc)

        if self.use_vector_search:
            self._index_documents([doc])

        # Сохраняем в историю обучения
        record = LearningRecord(
            document_hash=doc_hash,
            document_type=document_type,
            added_at=metadata['added_at'],
            source=source,
            parties=parties or [],
            keywords=keywords
        )
        self.learning_history.append(record)
        self.learned_hashes.add(doc_hash)
        self._save_learning_history()

        logger.info(f"✅ Learned from document: {document_type} ({source}), "
                    f"hash={doc_hash[:8]}...")

        return {
            'success': True,
            'hash': doc_hash,
            'document_type': document_type,
            'keywords': keywords,
            'total_learned': len(self.learning_history),
            'message': f'Документ добавлен в базу знаний (всего: {len(self.learning_history)})'
        }

    def get_learning_stats(self) -> dict[str, Any]:
        """Получение статистики обучения."""
        # Статистика по типам документов
        type_counts = {}
        source_counts = {}
        keyword_counts = {}

        for record in self.learning_history:
            # По типам
            doc_type = record.document_type or 'unknown'
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

            # По источникам
            source = record.source or 'unknown'
            source_counts[source] = source_counts.get(source, 0) + 1

            # По ключевым словам
            for kw in record.keywords:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        # Топ ключевые слова
        top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            'total_learned_documents': len(self.learning_history),
            'learning_enabled': self.enable_learning,
            'documents_by_type': type_counts,
            'documents_by_source': source_counts,
            'top_keywords': dict(top_keywords),
            'last_learning': self.learning_history[-1].added_at if self.learning_history else None,
            'vector_search_enabled': self.use_vector_search
        }

    def forget_document(self, document_hash: str) -> bool:
        """Удаление документа из базы знаний по хэшу.

        Args:
            document_hash: Хэш документа для удаления

        Returns:
            True если документ успешно удалён
        """
        if document_hash not in self.learned_hashes:
            return False

        # Удаляем из ChromaDB
        if self.use_vector_search and self.collection:
            try:
                doc_id = f"doc_{hash(document_hash)}"
                self.collection.delete(ids=[doc_id])
            except Exception as e:
                logger.error(f"Failed to delete from ChromaDB: {e}")

        # Удаляем из списка документов
        self.documents = [
            doc for doc in self.documents
            if doc.metadata.get('hash') != document_hash
        ]

        # Удаляем из истории
        self.learning_history = [
            lr for lr in self.learning_history
            if lr.document_hash != document_hash
        ]
        self.learned_hashes.discard(document_hash)
        self._save_learning_history()

        logger.info(f"🗑️ Forgot document: {document_hash[:8]}...")
        return True

    # ========== PRE-RETRIEVAL ==========

    def expand_query(self, query: str) -> str:
        """Pre-Retrieval: Расширение запроса синонимами

        Добавляет юридические синонимы к запросу для улучшения recall
        """
        expanded = query.lower()
        additions = []

        for term, synonyms in self.LEGAL_SYNONYMS.items():
            if term in expanded:
                additions.extend(synonyms)

        if additions:
            expanded = f"{query} {' '.join(additions)}"
            logger.debug(f"Query expanded: '{query}' -> '{expanded}'")

        return expanded

    def normalize_text(self, text: str) -> str:
        """Pre-Retrieval: Нормализация текста"""
        # Приводим к нижнему регистру
        text = text.lower()
        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text)
        # Убираем спецсимволы кроме букв и цифр
        text = re.sub(r'[^\w\s]', ' ', text)
        return text.strip()

    # ========== RETRIEVAL ==========

    def retrieve(self, query: str, k: int = 5) -> list[Document]:
        """Поиск документов (векторный или keyword-based).

        Args:
            query: Поисковый запрос
            k: Количество результатов

        Returns:
            Список релевантных документов
        """
        if self.use_vector_search:
            return self._vector_retrieve(query, k)
        return self._keyword_retrieve(query, k)

    def _vector_retrieve(self, query: str, k: int = 5) -> list[Document]:
        """Векторный поиск через ChromaDB.

        Args:
            query: Поисковый запрос
            k: Количество результатов

        Returns:
            Список релевантных документов
        """
        try:
            # Pre-Retrieval: расширяем запрос
            expanded_query = self.expand_query(query)

            # Генерируем эмбеддинг запроса
            query_embedding = self.embedder.encode([expanded_query])[0]

            # Поиск в ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=min(k, self.collection.count()),
                include=["documents", "metadatas", "distances"]
            )

            # Преобразуем результаты в Document
            documents = []
            if results and results['documents']:
                for i, doc_text in enumerate(results['documents'][0]):
                    # Конвертируем distance в similarity score (cosine)
                    distance = results['distances'][0][i] if results['distances'] else 0
                    score = 1 - distance  # cosine distance -> similarity

                    documents.append(Document(
                        content=doc_text,
                        metadata=results['metadatas'][0][i] if results['metadatas'] else {},
                        score=score
                    ))

            logger.debug(f"Vector search found {len(documents)} documents")
            return documents

        except Exception as e:
            logger.error(f"Vector search failed: {e}, falling back to keywords")
            return self._keyword_retrieve(query, k)

    def _keyword_retrieve(self, query: str, k: int = 5) -> list[Document]:
        """Fallback: поиск по ключевым словам.

        Args:
            query: Поисковый запрос
            k: Количество результатов

        Returns:
            Список релевантных документов
        """
        # Pre-Retrieval: расширяем запрос
        expanded_query = self.expand_query(query)
        normalized_query = self.normalize_text(expanded_query)
        query_words = set(normalized_query.split())

        results = []
        for doc in self.documents:
            normalized_content = self.normalize_text(doc.content)
            content_words = set(normalized_content.split())

            # Считаем совпадения
            matches = query_words & content_words
            if matches:
                score = len(matches) / len(query_words)
                results.append(Document(
                    content=doc.content,
                    metadata=doc.metadata,
                    score=score
                ))

        # Сортируем по релевантности
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:k]

    # ========== POST-RETRIEVAL ==========

    def rerank(self, documents: list[Document], query: str) -> list[Document]:
        """Post-Retrieval: Переранжирование документов

        Улучшает точность через:
        - Учёт позиции ключевых слов (ближе к началу = лучше)
        - Учёт плотности совпадений
        - Бонус за юридические термины
        """
        query_words = set(self.normalize_text(query).split())

        reranked = []
        for doc in documents:
            content_lower = doc.content.lower()
            score = doc.score

            # Бонус за юридические ключевые слова
            legal_bonus = 0
            for keyword in self.CONTRACT_KEYWORDS:
                if keyword in content_lower:
                    legal_bonus += 0.1

            # Бонус за точные совпадения фраз
            for word in query_words:
                if word in content_lower:
                    # Позиция в документе (ближе к началу = лучше)
                    position = content_lower.find(word)
                    position_bonus = max(0, 1 - position / 1000) * 0.1
                    score += position_bonus

            # Итоговый скор
            final_score = min(1.0, score + legal_bonus)

            reranked.append(Document(
                content=doc.content,
                metadata=doc.metadata,
                score=final_score
            ))

        # Сортируем по новому скору
        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked

    def filter_relevant(self, documents: list[Document],
                       min_score: float = 0.1) -> list[Document]:
        """Post-Retrieval: Фильтрация нерелевантных документов"""
        return [doc for doc in documents if doc.score >= min_score]

    # ========== MAIN API ==========

    def search(self, query: str, k: int = 5,
               min_relevance: float = 0.1) -> list[Document]:
        """Полный RAG поиск: Pre-Retrieval -> Retrieval -> Post-Retrieval

        Args:
            query: Поисковый запрос
            k: Количество результатов
            min_relevance: Минимальная релевантность

        Returns:
            Список релевантных документов после reranking
        """
        # 1. Retrieval (включает Pre-Retrieval)
        results = self.retrieve(query, k=k*2)  # Берём больше для reranking

        # 2. Post-Retrieval: Rerank
        results = self.rerank(results, query)

        # 3. Post-Retrieval: Filter
        results = self.filter_relevant(results, min_relevance)

        return results[:k]

    def is_contract(self, text: str) -> tuple:
        """Определяет, является ли текст договором

        Returns:
            (is_contract, confidence)
        """
        text_lower = text.lower()
        matches = sum(1 for kw in self.CONTRACT_KEYWORDS if kw in text_lower)
        confidence = min(1.0, matches / 5)  # 5 ключевых слов = 100% уверенность

        is_contract = confidence >= 0.4  # Минимум 2 ключевых слова
        return is_contract, confidence

    def find_similar_template(self, contract_text: str) -> Document | None:
        """Находит наиболее похожий шаблон договора"""
        results = self.search(contract_text[:500], k=1)  # Используем начало договора
        return results[0] if results else None

    def get_stats(self) -> dict[str, Any]:
        """Статистика RAG системы."""
        stats = {
            'total_templates': len(self.documents),
            'templates_dir': str(self.templates_dir),
            'synonyms_count': len(self.LEGAL_SYNONYMS),
            'keywords_count': len(self.CONTRACT_KEYWORDS),
            'vector_search_enabled': self.use_vector_search,
        }

        if self.use_vector_search and self.collection:
            stats['indexed_documents'] = self.collection.count()
            stats['embedding_model'] = self.EMBEDDING_MODEL

        return stats

    def add_document(self, content: str, metadata: dict | None = None) -> bool:
        """Добавление документа в индекс.

        Args:
            content: Текст документа
            metadata: Метаданные документа

        Returns:
            True если успешно добавлен
        """
        if not content:
            return False

        doc = Document(
            content=content,
            metadata=metadata or {'type': 'dynamic'}
        )
        self.documents.append(doc)

        if self.use_vector_search:
            self._index_documents([doc])

        return True

    def clear_index(self):
        """Очистка индекса ChromaDB."""
        if self.use_vector_search and self.collection:
            try:
                # Удаляем и пересоздаём коллекцию
                self.chroma_client.delete_collection("legal_documents")
                self.collection = self.chroma_client.create_collection(
                    name="legal_documents",
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info("ChromaDB index cleared")
            except Exception as e:
                logger.error(f"Failed to clear index: {e}")


