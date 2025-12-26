"""Модуль для работы с векторными embeddings шаблонов"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy не установлен. Установите: pip install numpy")

# Проверяем доступность sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers не установлен. Установите: pip install sentence-transformers")

# Fallback: простая TF-IDF реализация
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn не установлен. Установите: pip install scikit-learn")


class TemplateEmbeddings:
    """Класс для работы с векторными представлениями шаблонов"""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Инициализация системы embeddings
        
        Args:
            cache_dir: Директория для кэширования embeddings
        """
        self.cache_dir = cache_dir or Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.embeddings_model = None
        self.template_vectors = {}  # {template_name: vector}
        self.template_texts = {}    # {template_name: text}
        self.use_sentence_transformers = False
        
        self._init_embeddings_model()
    
    def _init_embeddings_model(self):
        """Инициализация модели для embeddings"""
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                # Используем русскоязычную модель
                model_name = "intfloat/multilingual-e5-base"  # Хорошая мультиязычная модель
                # Альтернатива: "cointegrated/rubert-base-cased-dpipeline" для русского
                logger.info(f"Загрузка модели embeddings: {model_name}")
                self.embeddings_model = SentenceTransformer(model_name)
                self.use_sentence_transformers = True
                logger.info("✅ Модель embeddings загружена (sentence-transformers)")
            except Exception as e:
                logger.warning(f"Ошибка загрузки sentence-transformers: {e}")
                self._init_tfidf_fallback()
        else:
            self._init_tfidf_fallback()
    
    def _init_tfidf_fallback(self):
        """Инициализация TF-IDF как fallback"""
        if SKLEARN_AVAILABLE:
            self.embeddings_model = TfidfVectorizer(
                max_features=5000,
                ngram_range=(1, 2),
                stop_words=None  # Будем использовать русские стоп-слова
            )
            logger.info("✅ Используется TF-IDF для embeddings")
        else:
            logger.warning("⚠️ Нет доступных библиотек для embeddings. Используется простой поиск.")
    
    def load_templates(self, templates: Dict[str, Dict]):
        """
        Загрузка шаблонов и создание embeddings
        
        Args:
            templates: Словарь шаблонов {name: {content: str, ...}}
        """
        self.template_texts = {}
        
        for name, template_data in templates.items():
            content = template_data.get('content', '')
            # Создаем краткое описание для embedding
            # Используем первые 2000 символов + название файла
            text_for_embedding = f"{name} {content[:2000]}"
            self.template_texts[name] = text_for_embedding
        
        # Создаем embeddings
        self._create_embeddings()
    
    def _create_embeddings(self):
        """Создание векторных представлений для всех шаблонов"""
        if not self.template_texts:
            return
        
        if not NUMPY_AVAILABLE:
            logger.error("numpy не установлен, невозможно создать embeddings")
            return
        
        cache_file = self.cache_dir / "template_embeddings.pkl"
        
        # Проверяем кэш
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    if cached_data.get('template_texts') == self.template_texts:
                        self.template_vectors = cached_data.get('vectors', {})
                        logger.info("✅ Загружены embeddings из кэша")
                        return
            except Exception as e:
                logger.warning(f"Ошибка загрузки кэша: {e}")
        
        # Создаем новые embeddings
        logger.info("Создание векторных представлений шаблонов...")
        
        if self.use_sentence_transformers and self.embeddings_model:
            # Используем sentence-transformers
            texts = list(self.template_texts.values())
            names = list(self.template_texts.keys())
            
            # Создаем embeddings батчами для экономии памяти
            batch_size = 32
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                embeddings = self.embeddings_model.encode(
                    batch,
                    show_progress_bar=True,
                    convert_to_numpy=True
                )
                all_embeddings.extend(embeddings)
            
            # Нормализуем векторы для cosine similarity
            for name, embedding in zip(names, all_embeddings):
                norm = np.linalg.norm(embedding)
                self.template_vectors[name] = embedding / norm if norm > 0 else embedding
                
        elif SKLEARN_AVAILABLE and isinstance(self.embeddings_model, TfidfVectorizer):
            # Используем TF-IDF
            texts = list(self.template_texts.values())
            names = list(self.template_texts.keys())
            
            tfidf_matrix = self.embeddings_model.fit_transform(texts)
            
            # Сохраняем векторы
            for name, vector in zip(names, tfidf_matrix):
                self.template_vectors[name] = vector.toarray().flatten()
        
        # Сохраняем в кэш
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump({
                    'template_texts': self.template_texts,
                    'vectors': self.template_vectors
                }, f)
            logger.info(f"✅ Embeddings сохранены в кэш: {cache_file}")
        except Exception as e:
            logger.warning(f"Ошибка сохранения кэша: {e}")
        
        logger.info(f"✅ Создано {len(self.template_vectors)} векторных представлений")
    
    def find_similar_templates(self, query_text: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Поиск похожих шаблонов по запросу
        
        Args:
            query_text: Текст для поиска
            top_k: Количество лучших результатов
        
        Returns:
            Список кортежей (имя_шаблона, оценка_схожести)
        """
        if not self.template_vectors:
            return []
        
        if not NUMPY_AVAILABLE:
            logger.warning("numpy не установлен, невозможно выполнить векторный поиск")
            return []
        
        # Создаем embedding для запроса
        if self.use_sentence_transformers and self.embeddings_model:
            query_embedding = self.embeddings_model.encode(
                [query_text],
                convert_to_numpy=True
            )[0]
            # Нормализуем
            norm = np.linalg.norm(query_embedding)
            query_embedding = query_embedding / norm if norm > 0 else query_embedding
            
            # Вычисляем cosine similarity
            similarities = []
            for name, template_vector in self.template_vectors.items():
                similarity = np.dot(query_embedding, template_vector)
                similarities.append((name, float(similarity)))
                
        elif SKLEARN_AVAILABLE and isinstance(self.embeddings_model, TfidfVectorizer):
            # TF-IDF подход
            query_vector = self.embeddings_model.transform([query_text])
            similarities = []
            
            for name, template_vector in self.template_vectors.items():
                # Преобразуем в нужный формат
                if hasattr(template_vector, 'toarray'):
                    template_array = template_vector.toarray()
                else:
                    template_array = template_vector.reshape(1, -1)
                
                similarity = cosine_similarity(query_vector, template_array)[0][0]
                similarities.append((name, float(similarity)))
        else:
            return []
        
        # Сортируем по убыванию схожести
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]
    
    def get_template_embedding(self, template_name: str) -> Optional[np.ndarray]:
        """Получение embedding для конкретного шаблона"""
        return self.template_vectors.get(template_name)
    
    def clear_cache(self):
        """Очистка кэша embeddings"""
        cache_file = self.cache_dir / "template_embeddings.pkl"
        if cache_file.exists():
            cache_file.unlink()
            logger.info("Кэш embeddings очищен")

