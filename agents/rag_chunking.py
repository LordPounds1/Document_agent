"""RAG Chunking Pipeline - умное разбиение документов на чанки для RAG систем"""

import logging
import re
from typing import List, Dict, Optional, Tuple
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter, CharacterTextSplitter

logger = logging.getLogger(__name__)


class RAGChunkingPipeline:
    """Умное разбиение документов на чанки для RAG с различными стратегиями"""
    
    def __init__(self, 
                 chunk_size: int = 1024,
                 chunk_overlap: int = 256,
                 strategy: str = "recursive"):
        """
        Инициализация pipeline
        
        Args:
            chunk_size: Размер чанка в символах (default: 1024)
            chunk_overlap: Перекрытие между чанками (default: 256)
            strategy: Стратегия разбиения - "recursive" (умное) или "simple" (простое)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy
        
        self._init_splitters()
    
    def _init_splitters(self):
        """Инициализация text splitters"""
        # Рекурсивный splitter для умного разбиения
        self.recursive_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=[
                "\n\n",           # Разделитель параграфов
                "\n",             # Разделитель строк
                ". ",             # Разделитель предложений
                " ",              # Разделитель слов
                ""                # Fallback: по символам
            ],
            length_function=len,
        )
        
        # Простой character splitter
        self.simple_splitter = CharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separator="\n",
            length_function=len,
        )
        
        logger.info(f"Chunking pipeline инициализирован: size={self.chunk_size}, overlap={self.chunk_overlap}, strategy={self.strategy}")
    
    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        Разбиение документов на чанки
        
        Args:
            documents: Список LangChain Documents
        
        Returns:
            Список документов-чанков с метаданными
        """
        if self.strategy == "recursive":
            return self._split_recursive(documents)
        elif self.strategy == "semantic":
            return self._split_semantic(documents)
        else:
            return self._split_simple(documents)
    
    def _split_recursive(self, documents: List[Document]) -> List[Document]:
        """Рекурсивное разбиение - самое умное"""
        chunks = []
        
        for doc in documents:
            # Используем рекурсивный splitter
            texts = self.recursive_splitter.split_text(doc.page_content)
            
            for i, text in enumerate(texts):
                chunk_doc = Document(
                    page_content=text,
                    metadata={
                        **doc.metadata,
                        'chunk_id': i,
                        'chunk_count': len(texts),
                        'strategy': 'recursive'
                    }
                )
                chunks.append(chunk_doc)
        
        logger.info(f"Recursive split: {len(documents)} документов → {len(chunks)} чанков")
        return chunks
    
    def _split_semantic(self, documents: List[Document]) -> List[Document]:
        """
        Семантическое разбиение - разбивает по смыслу документа
        Анализирует структуру и разбивает по разделам, заголовкам и т.д.
        """
        chunks = []
        
        for doc in documents:
            # Проверяем есть ли информация о разделах
            if doc.metadata.get('type') == 'section':
                # Это уже раздел - разбиваем на подчанки
                texts = self.recursive_splitter.split_text(doc.page_content)
                
                for i, text in enumerate(texts):
                    chunk_doc = Document(
                        page_content=text,
                        metadata={
                            **doc.metadata,
                            'chunk_id': i,
                            'chunk_count': len(texts),
                            'strategy': 'semantic'
                        }
                    )
                    chunks.append(chunk_doc)
            else:
                # Пытаемся найти естественные разделители
                # Ищем заголовки (строки начинающиеся с #, точка.Слово, и т.д.)
                sections = self._extract_semantic_sections(doc.page_content)
                
                chunk_id = 0
                for section_title, section_text in sections:
                    # Разбиваем каждый раздел на чанки
                    texts = self.recursive_splitter.split_text(section_text)
                    
                    for i, text in enumerate(texts):
                        chunk_doc = Document(
                            page_content=text,
                            metadata={
                                **doc.metadata,
                                'semantic_section': section_title,
                                'chunk_id': chunk_id,
                                'strategy': 'semantic'
                            }
                        )
                        chunks.append(chunk_doc)
                        chunk_id += 1
        
        logger.info(f"Semantic split: {len(documents)} документов → {len(chunks)} чанков")
        return chunks
    
    def _split_simple(self, documents: List[Document]) -> List[Document]:
        """Простое разбиение - по разделителю"""
        chunks = []
        
        for doc in documents:
            texts = self.simple_splitter.split_text(doc.page_content)
            
            for i, text in enumerate(texts):
                chunk_doc = Document(
                    page_content=text,
                    metadata={
                        **doc.metadata,
                        'chunk_id': i,
                        'chunk_count': len(texts),
                        'strategy': 'simple'
                    }
                )
                chunks.append(chunk_doc)
        
        logger.info(f"Simple split: {len(documents)} документов → {len(chunks)} чанков")
        return chunks
    
    def _extract_semantic_sections(self, text: str) -> List[Tuple[str, str]]:
        """
        Извлечение семантических разделов из текста
        
        Returns:
            Список (заголовок_раздела, текст_раздела)
        """
        sections = []
        
        # Ищем заголовки (markdown стиль: # Заголовок)
        heading_pattern = r'^(#+)\s+(.+?)$'
        lines = text.split('\n')
        
        current_section = "Основной текст"
        current_content = []
        
        for line in lines:
            heading_match = re.match(heading_pattern, line)
            
            if heading_match:
                # Нашли новый заголовок
                if current_content:
                    sections.append((current_section, '\n'.join(current_content)))
                
                current_section = heading_match.group(2)
                current_content = []
            else:
                if line.strip():  # Только непустые строки
                    current_content.append(line)
        
        # Добавляем последний раздел
        if current_content:
            sections.append((current_section, '\n'.join(current_content)))
        
        # Если не нашли разделов, возвращаем весь текст как один раздел
        if not sections:
            sections = [("Основной текст", text)]
        
        return sections
    
    def merge_small_chunks(self, chunks: List[Document], min_size: int = 512) -> List[Document]:
        """
        Объединение маленьких чанков с соседними для избежания фрагментации
        
        Args:
            chunks: Список чанков
            min_size: Минимальный размер (меньше объединяются с соседями)
        
        Returns:
            Оптимизированный список чанков
        """
        if not chunks:
            return chunks
        
        merged = []
        i = 0
        
        while i < len(chunks):
            current_chunk = chunks[i]
            
            # Если чанк маленький и это не последний чанк
            if len(current_chunk.page_content) < min_size and i < len(chunks) - 1:
                # Объединяем с следующим чанком
                next_chunk = chunks[i + 1]
                merged_content = current_chunk.page_content + "\n\n" + next_chunk.page_content
                
                merged_chunk = Document(
                    page_content=merged_content,
                    metadata={
                        **current_chunk.metadata,
                        'merged': True,
                        'original_chunks': 2
                    }
                )
                merged.append(merged_chunk)
                i += 2  # Пропускаем следующий чанк
            else:
                merged.append(current_chunk)
                i += 1
        
        logger.info(f"Merge: {len(chunks)} → {len(merged)} чанков (min_size={min_size})")
        return merged
    
    def add_context_windows(self, chunks: List[Document], window_size: int = 2) -> List[Document]:
        """
        Добавление контекстных окон - добавляет соседние чанки в метаданные
        Полезно для более полного понимания контекста при работе с LLM
        
        Args:
            chunks: Список чанков
            window_size: Количество соседних чанков с каждой стороны
        
        Returns:
            Чанки с добавленной информацией о соседях
        """
        for i, chunk in enumerate(chunks):
            prev_chunks = chunks[max(0, i - window_size):i]
            next_chunks = chunks[i + 1:min(len(chunks), i + window_size + 1)]
            
            chunk.metadata['prev_chunks'] = len(prev_chunks)
            chunk.metadata['next_chunks'] = len(next_chunks)
            
            # Добавляем IDs соседних чанков для быстрого доступа
            chunk.metadata['prev_chunk_ids'] = [c.metadata.get('chunk_id', -1) for c in prev_chunks]
            chunk.metadata['next_chunk_ids'] = [c.metadata.get('chunk_id', -1) for c in next_chunks]
        
        logger.info(f"Added context windows (window_size={window_size})")
        return chunks
    
    def process_pipeline(self, 
                        documents: List[Document],
                        merge_small: bool = True,
                        add_context: bool = True) -> List[Document]:
        """
        Полная pipeline обработки документов
        
        Args:
            documents: Входные документы
            merge_small: Объединять маленькие чанки
            add_context: Добавлять контекстные окна
        
        Returns:
            Обработанные и готовые к использованию в RAG чанки
        """
        logger.info(f"📊 Запуск полной pipeline обработки ({len(documents)} документов)")
        
        # Этап 1: Разбиение на чанки
        chunks = self.split_documents(documents)
        logger.info(f"  ✓ Этап 1: Разбиение → {len(chunks)} чанков")
        
        # Этап 2: Объединение маленьких чанков (опционально)
        if merge_small:
            chunks = self.merge_small_chunks(chunks)
            logger.info(f"  ✓ Этап 2: Объединение → {len(chunks)} чанков")
        
        # Этап 3: Добавление контекстных окон (опционально)
        if add_context:
            chunks = self.add_context_windows(chunks)
            logger.info(f"  ✓ Этап 3: Контекст добавлен")
        
        logger.info(f"✅ Pipeline завершен: {len(chunks)} финальных чанков")
        return chunks
