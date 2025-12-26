"""Vector Store для RAG - хранение и поиск embeddings с FAISS/Chroma"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pickle
import json

from langchain.schema import Document
from langchain.embeddings.base import Embeddings

logger = logging.getLogger(__name__)

try:
    from langchain.vectorstores import FAISS
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS не установлен. Установите: pip install faiss-cpu")

try:
    from langchain.vectorstores import Chroma
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("Chroma не установлен. Установите: pip install chromadb")


class RAGVectorStore:
    """
    Vector Store для RAG с поддержкой FAISS и Chroma
    Сохраняет embeddings документов и позволяет быстрый поиск по семантике
    """
    
    def __init__(self, 
                 embeddings: Embeddings,
                 store_type: str = "faiss",
                 store_path: str = "data/vector_store"):
        """
        Инициализация Vector Store
        
        Args:
            embeddings: LangChain Embeddings объект (sentence-transformers)
            store_type: "faiss" или "chroma"
            store_path: Путь для сохранения индекса
        """
        self.embeddings = embeddings
        self.store_type = store_type
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        self.vector_store = None
        self.metadata_store = {}  # Дополнительные метаданные
        
        self._init_store()
    
    def _init_store(self):
        """Инициализация хранилища"""
        logger.info(f"Инициализация {self.store_type} Vector Store")
        
        if self.store_type == "faiss" and FAISS_AVAILABLE:
            # FAISS индекс будет создан при добавлении документов
            logger.info("✅ FAISS Vector Store готов")
        
        elif self.store_type == "chroma" and CHROMA_AVAILABLE:
            # Chroma индекс будет создан при добавлении документов
            logger.info("✅ Chroma Vector Store готов")
        
        else:
            logger.error(f"❌ {self.store_type} не доступен")
    
    def add_documents(self, documents: List[Document], batch_size: int = 32) -> bool:
        """
        Добавление документов в Vector Store
        
        Args:
            documents: Список LangChain Documents с embeddings
            batch_size: Размер батча для обработки
        
        Returns:
            True если успешно, False иначе
        """
        if not documents:
            logger.warning("Нет документов для добавления")
            return False
        
        try:
            logger.info(f"📊 Добавление {len(documents)} документов в {self.store_type} Vector Store")
            
            if self.store_type == "faiss" and FAISS_AVAILABLE:
                # Батч обработка для больших наборов документов
                for i in range(0, len(documents), batch_size):
                    batch = documents[i:i + batch_size]
                    
                    if self.vector_store is None:
                        # Создаем первый индекс
                        self.vector_store = FAISS.from_documents(
                            batch,
                            self.embeddings
                        )
                    else:
                        # Добавляем в существующий индекс
                        self.vector_store.add_documents(batch)
                    
                    logger.info(f"  ✓ Обработано {min(i + batch_size, len(documents))}/{len(documents)}")
                
                # Сохраняем индекс
                self._save_faiss_index()
                logger.info(f"✅ FAISS индекс сохранен: {len(documents)} документов")
                return True
            
            elif self.store_type == "chroma" and CHROMA_AVAILABLE:
                if self.vector_store is None:
                    self.vector_store = Chroma.from_documents(
                        documents,
                        self.embeddings,
                        persist_directory=str(self.store_path / "chroma")
                    )
                else:
                    for doc in documents:
                        self.vector_store.add_documents([doc])
                
                self.vector_store.persist()
                logger.info(f"✅ Chroma индекс сохранен: {len(documents)} документов")
                return True
            
            else:
                logger.error(f"Vector Store type {self.store_type} не поддерживается")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка добавления документов: {e}")
            return False
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[Document, float]]:
        """
        Поиск документов по семантическому сходству
        
        Args:
            query: Текст запроса
            top_k: Количество результатов
        
        Returns:
            Список (Document, score) отсортированный по релевантности
        """
        if self.vector_store is None:
            logger.warning("Vector Store не инициализирован")
            return []
        
        try:
            if self.store_type == "faiss":
                # FAISS возвращает документы с расстояниями
                results = self.vector_store.similarity_search_with_scores(query, k=top_k)
                return results
            
            elif self.store_type == "chroma":
                # Chroma возвращает документы с расстояниями
                results = self.vector_store.similarity_search_with_relevance_scores(query, k=top_k)
                return results
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {e}")
            return []
    
    def search_multiple(self, queries: List[str], top_k: int = 5) -> Dict[str, List[Tuple[Document, float]]]:
        """
        Поиск по нескольким запросам (для pre-retrieval вариантов)
        
        Args:
            queries: Список запросов
            top_k: Количество результатов на запрос
        
        Returns:
            Словарь {query: [(Document, score), ...]}
        """
        results = {}
        
        for query in queries:
            results[query] = self.search(query, top_k)
        
        return results
    
    def _save_faiss_index(self):
        """Сохранение FAISS индекса на диск"""
        if self.vector_store is None:
            return
        
        try:
            save_path = self.store_path / "faiss_index"
            self.vector_store.save_local(str(save_path))
            logger.debug(f"FAISS индекс сохранен: {save_path}")
        except Exception as e:
            logger.warning(f"Ошибка сохранения FAISS индекса: {e}")
    
    def load_faiss_index(self):
        """Загрузка FAISS индекса с диска"""
        try:
            load_path = self.store_path / "faiss_index"
            if load_path.exists():
                self.vector_store = FAISS.load_local(
                    str(load_path),
                    self.embeddings
                )
                logger.info(f"✅ FAISS индекс загружен: {load_path}")
                return True
        except Exception as e:
            logger.warning(f"Ошибка загрузки FAISS индекса: {e}")
        
        return False
    
    def load_chroma_index(self):
        """Загрузка Chroma индекса с диска"""
        try:
            chroma_path = self.store_path / "chroma"
            if chroma_path.exists():
                self.vector_store = Chroma(
                    persist_directory=str(chroma_path),
                    embedding_function=self.embeddings
                )
                logger.info(f"✅ Chroma индекс загружен: {chroma_path}")
                return True
        except Exception as e:
            logger.warning(f"Ошибка загрузки Chroma индекса: {e}")
        
        return False
    
    def load(self):
        """Загрузка сохраненного индекса"""
        if self.store_type == "faiss":
            return self.load_faiss_index()
        elif self.store_type == "chroma":
            return self.load_chroma_index()
        
        return False
    
    def get_stats(self) -> Dict:
        """Получение статистики Vector Store"""
        stats = {
            'store_type': self.store_type,
            'initialized': self.vector_store is not None,
            'store_path': str(self.store_path)
        }
        
        # Попытка получить информацию об индексе
        try:
            if self.store_type == "faiss" and self.vector_store:
                stats['index_size'] = self.vector_store.index.ntotal if hasattr(self.vector_store, 'index') else "unknown"
            
            elif self.store_type == "chroma" and self.vector_store:
                # Chroma не предоставляет простой способ получить размер индекса
                stats['index_size'] = "see vector store"
        
        except Exception as e:
            logger.debug(f"Ошибка получения статистики: {e}")
        
        return stats
    
    def clear(self):
        """Очистка Vector Store"""
        try:
            if self.store_type == "faiss":
                # FAISS не имеет встроенного метода очистки, пересоздаем
                self.vector_store = None
                
                # Удаляем сохраненные файлы
                save_path = self.store_path / "faiss_index"
                if save_path.exists():
                    import shutil
                    shutil.rmtree(save_path)
            
            elif self.store_type == "chroma":
                if self.vector_store:
                    self.vector_store._client.delete_collection(self.vector_store._collection.name)
                    self.vector_store = None
            
            logger.info("Vector Store очищен")
        except Exception as e:
            logger.warning(f"Ошибка очистки Vector Store: {e}")
