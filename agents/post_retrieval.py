"""Post-Retrieval Pipeline - обработка полученных документов перед подачей в LLM"""

import logging
from typing import List, Dict, Optional
from langchain.schema import Document

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import CrossEncoder
    CROSSENCODER_AVAILABLE = True
except ImportError:
    CROSSENCODER_AVAILABLE = False
    logger.warning("sentence-transformers с CrossEncoder не установлен")


class PostRetrievalPipeline:
    """
    Post-retrieval обработка документов для улучшения качества RAG.
    Реализует три техники:
    1. Rerank - переранжирование документов по релевантности
    2. Summary - абстрактное резюме каждого документа
    3. Fusion - объединение похожих документов
    """
    
    def __init__(self, use_reranking: bool = True):
        """
        Инициализация pipeline
        
        Args:
            use_reranking: Использовать CrossEncoder для переранжирования
        """
        self.use_reranking = use_reranking
        self.reranker = None
        
        if use_reranking:
            self._init_reranker()
    
    def _init_reranker(self):
        """Инициализация CrossEncoder для переранжирования"""
        if not CROSSENCODER_AVAILABLE:
            logger.warning("CrossEncoder не доступен, переранжирование отключено")
            self.use_reranking = False
            return
        
        try:
            # Используем русскоязычную модель для переранжирования
            self.reranker = CrossEncoder('cross-encoder/mmarco-mMiniLMv2-L12-H384-v1')
            logger.info("✅ CrossEncoder для переранжирования инициализирован")
        except Exception as e:
            logger.warning(f"Ошибка инициализации CrossEncoder: {e}")
            self.use_reranking = False
    
    def process(self, 
                documents: List[Document],
                query: str,
                top_k: int = 5,
                strategies: List[str] = None) -> List[Document]:
        """
        Главная функция обработки документов
        
        Args:
            documents: Список полученных документов из поиска
            query: Исходный запрос пользователя
            top_k: Количество финальных документов для возврата
            strategies: Список применяемых стратегий - ["rerank", "summary", "fusion"]
        
        Returns:
            Обработанный и отфильтрованный список документов
        """
        if not documents:
            logger.warning("Нет документов для обработки")
            return []
        
        if strategies is None:
            strategies = ["rerank", "fusion"]  # По умолчанию используем rerank и fusion
        
        logger.info(f"[POST-RETRIEVAL] Обработка {len(documents)} документов (стратегии: {strategies})")
        processed = documents
        
        # Этап 1: Переранжирование
        if "rerank" in strategies:
            processed = self._rerank(processed, query)
        
        # Этап 2: Резюме
        if "summary" in strategies:
            processed = self._add_summaries(processed)
        
        # Этап 3: Объединение/Fusion
        if "fusion" in strategies:
            processed = self._fusion(processed, query)
        
        # Возвращаем top_k документов
        result = processed[:top_k]
        logger.info(f"✅ Post-retrieval завершен: возвращено {len(result)} документов")
        
        return result
    
    def _rerank(self, documents: List[Document], query: str) -> List[Document]:
        """
        Переранжирование документов используя CrossEncoder
        
        Более точный подход чем семантический поиск - использует пары (query, document)
        для определения релевантности
        """
        if not self.use_reranking or not documents:
            return documents
        
        try:
            logger.info(f"  [Rerank] Переранжирование {len(documents)} документов...")
            
            # Подготавливаем пары (query, document_content)
            pairs = [
                [query, doc.page_content[:512]]  # Берем первые 512 символов для скорости
                for doc in documents
            ]
            
            # Получаем scores от CrossEncoder
            scores = self.reranker.predict(pairs)
            
            # Добавляем scores в метаданные
            for doc, score in zip(documents, scores):
                doc.metadata['rerank_score'] = float(score)
            
            # Сортируем по scores (descending)
            reranked = sorted(documents, key=lambda x: x.metadata.get('rerank_score', 0), reverse=True)
            
            logger.info(f"  ✓ Переранжирование завершено")
            return reranked
        
        except Exception as e:
            logger.warning(f"Ошибка переранжирования: {e}")
            return documents
    
    def _add_summaries(self, documents: List[Document]) -> List[Document]:
        """
        Добавление резюме к каждому документу (extractive)
        
        Extractive summary - выделение наиболее важных предложений из документа
        """
        for doc in documents:
            try:
                summary = self._extract_summary(doc.page_content)
                doc.metadata['summary'] = summary
            except Exception as e:
                logger.debug(f"Ошибка создания резюме: {e}")
                doc.metadata['summary'] = doc.page_content[:200]
        
        logger.info(f"  ✓ Резюме добавлены ко всем документам")
        return documents
    
    def _extract_summary(self, text: str, num_sentences: int = 3) -> str:
        """
        Extractive summary - выбор важнейших предложений
        
        Простая реализация: берет первые и последние предложения как наиболее важные
        """
        # Разделяем на предложения
        sentences = text.split('.')
        
        if len(sentences) <= num_sentences:
            return text
        
        # Берем первые и последние предложения
        important = []
        
        # Первое предложение (часто содержит суть)
        important.append(sentences[0])
        
        # Последние предложения (часто содержат выводы)
        for s in sentences[-num_sentences+1:]:
            if s.strip():
                important.append(s)
        
        summary = '.'.join(important) + '.'
        return summary.strip()
    
    def _fusion(self, documents: List[Document], query: str) -> List[Document]:
        """
        Fusion - объединение похожих документов для избежания дубликатов
        
        Объединяет документы с очень похожим контентом в один с объединенным текстом
        """
        if len(documents) <= 1:
            return documents
        
        try:
            logger.info(f"  [Fusion] Объединение похожих документов...")
            
            fused = []
            used_indices = set()
            
            for i, doc1 in enumerate(documents):
                if i in used_indices:
                    continue
                
                # Проверяем сходство с другими документами
                similar_docs = [doc1]
                
                for j, doc2 in enumerate(documents[i+1:], start=i+1):
                    if j in used_indices:
                        continue
                    
                    # Простая проверка сходства: совпадение ключевых слов
                    similarity = self._calculate_similarity(doc1.page_content, doc2.page_content)
                    
                    if similarity > 0.7:  # Пороговое значение
                        similar_docs.append(doc2)
                        used_indices.add(j)
                
                # Объединяем похожие документы
                if len(similar_docs) > 1:
                    fused_doc = self._merge_documents(similar_docs)
                    fused.append(fused_doc)
                else:
                    fused.append(doc1)
            
            logger.info(f"  ✓ Fusion: {len(documents)} → {len(fused)} документов")
            return fused
        
        except Exception as e:
            logger.warning(f"Ошибка fusion: {e}")
            return documents
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Простой расчет сходства по пересечению слов"""
        words1 = set(text1.lower().split()[:50])  # Берем первые 50 слов
        words2 = set(text2.lower().split()[:50])
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0
    
    def _merge_documents(self, documents: List[Document]) -> Document:
        """Объединение нескольких документов в один"""
        # Объединяем содержимое
        merged_content = "\n\n---\n\n".join([doc.page_content for doc in documents])
        
        # Объединяем метаданные
        merged_metadata = {**documents[0].metadata}
        merged_metadata['merged_count'] = len(documents)
        merged_metadata['merged_from'] = [
            doc.metadata.get('source', 'unknown') for doc in documents
        ]
        
        return Document(
            page_content=merged_content,
            metadata=merged_metadata
        )
    
    def deduplicate(self, documents: List[Document], threshold: float = 0.95) -> List[Document]:
        """
        Удаление полных дубликатов из списка документов
        
        Args:
            documents: Список документов
            threshold: Порог сходства для считания дубликатом
        
        Returns:
            Список уникальных документов
        """
        unique = []
        
        for doc in documents:
            is_duplicate = False
            
            for unique_doc in unique:
                similarity = self._calculate_similarity(doc.page_content, unique_doc.page_content)
                
                if similarity > threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(doc)
        
        logger.info(f"Deduplication: {len(documents)} → {len(unique)} документов")
        return unique
    
    def get_final_context(self, 
                         documents: List[Document],
                         max_tokens: int = 2000) -> str:
        """
        Подготовка финального контекста для LLM
        
        Объединяет документы в единый контекст с ограничением по токенам
        
        Args:
            documents: Обработанные документы
            max_tokens: Максимальное количество токенов (~4 символа на токен)
        
        Returns:
            Финальный контекст для подачи в LLM
        """
        context_parts = []
        current_length = 0
        max_chars = max_tokens * 4  # Приблизительное преобразование
        
        for doc in documents:
            source = doc.metadata.get('source', 'Unknown')
            summary = doc.metadata.get('summary', doc.page_content[:100])
            
            part = f"[{source}]\n{summary}\n"
            
            if current_length + len(part) <= max_chars:
                context_parts.append(part)
                current_length += len(part)
            else:
                break
        
        final_context = "\n---\n".join(context_parts)
        
        logger.info(f"Final context prepared: {len(context_parts)} документов, ~{current_length} символов")
        return final_context
