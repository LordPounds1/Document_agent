"""Упрощённый RAG Pipeline - Pre и Post Retrieval для юридических документов"""

import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Простой документ для RAG"""
    content: str
    metadata: Dict[str, Any]
    score: float = 0.0


class SimpleRAG:
    """Упрощённая RAG система с Pre и Post Retrieval
    
    Pre-Retrieval:
    - Расширение запроса синонимами юридических терминов
    - Нормализация текста
    
    Post-Retrieval:
    - Переранжирование по ключевым словам
    - Фильтрация по релевантности
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
    
    def __init__(self, templates_dir: str = "templates"):
        """
        Args:
            templates_dir: Директория с шаблонами договоров
        """
        self.templates_dir = Path(templates_dir)
        self.documents: List[Document] = []
        self._load_templates()
        
    def _load_templates(self):
        """Загрузка шаблонов договоров из директории"""
        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}")
            return
            
        loaded = 0
        for file_path in self.templates_dir.glob("*.docx"):
            try:
                content = self._read_docx(file_path)
                if content:
                    self.documents.append(Document(
                        content=content,
                        metadata={
                            'filename': file_path.name,
                            'path': str(file_path),
                            'type': 'template'
                        }
                    ))
                    loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")
        
        logger.info(f"Loaded {loaded} contract templates from {self.templates_dir}")
    
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
    
    def retrieve(self, query: str, k: int = 5) -> List[Document]:
        """Базовый поиск по ключевым словам
        
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
    
    def rerank(self, documents: List[Document], query: str) -> List[Document]:
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
    
    def filter_relevant(self, documents: List[Document], 
                       min_score: float = 0.1) -> List[Document]:
        """Post-Retrieval: Фильтрация нерелевантных документов"""
        return [doc for doc in documents if doc.score >= min_score]
    
    # ========== MAIN API ==========
    
    def search(self, query: str, k: int = 5, 
               min_relevance: float = 0.1) -> List[Document]:
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
    
    def find_similar_template(self, contract_text: str) -> Optional[Document]:
        """Находит наиболее похожий шаблон договора"""
        results = self.search(contract_text[:500], k=1)  # Используем начало договора
        return results[0] if results else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика RAG"""
        return {
            'total_templates': len(self.documents),
            'templates_dir': str(self.templates_dir),
            'synonyms_count': len(self.LEGAL_SYNONYMS),
            'keywords_count': len(self.CONTRACT_KEYWORDS)
        }

