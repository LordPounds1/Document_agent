"""Парсинг документов с использованием Docling - open-source решения для извлечения структурированного контента"""

import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import json

logger = logging.getLogger(__name__)

try:
    from docling.document_converter import DocumentConverter
    from docling.dataclasses import DoclingDocument, DocumentStream
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False
    logger.warning("docling не установлен. Установите: pip install docling")

from langchain.schema import Document


class DoclingParser:
    """Парсер документов с использованием Docling для структурированного извлечения контента"""
    
    def __init__(self):
        """Инициализация Docling парсера"""
        self.converter = None
        self._init_converter()
    
    def _init_converter(self):
        """Инициализация converter"""
        if not DOCLING_AVAILABLE:
            logger.error("Docling не установлен. Установите: pip install docling")
            return
        
        try:
            self.converter = DocumentConverter()
            logger.info("✅ Docling DocumentConverter инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Docling: {e}")
    
    def parse_document(self, file_path: str) -> Optional[DoclingDocument]:
        """
        Парсинг документа с Docling
        
        Args:
            file_path: Путь к документу (.pdf, .docx, .doc, .txt и т.д.)
        
        Returns:
            DoclingDocument с структурированным контентом или None
        """
        if not self.converter:
            logger.error("Converter не инициализирован")
            return None
        
        try:
            logger.info(f"Парсинг документа: {file_path}")
            result = self.converter.convert(file_path)
            
            if result.document:
                logger.info(f"✅ Документ успешно распарсен: {len(result.document.pages)} страниц")
                return result.document
            else:
                logger.warning(f"⚠️ Документ не был распарсен")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга документа: {e}")
            return None
    
    def extract_text_with_structure(self, file_path: str) -> Dict:
        """
        Извлечение текста с сохранением структуры документа
        
        Args:
            file_path: Путь к документу
        
        Returns:
            Словарь с:
            - full_text: Полный текст документа
            - structured_text: Текст с метаданными о структуре
            - sections: Разделы документа с заголовками
            - metadata: Метаданные документа
        """
        doc = self.parse_document(file_path)
        if not doc:
            return {
                "full_text": "",
                "structured_text": "",
                "sections": [],
                "metadata": {}
            }
        
        try:
            # Извлекаем полный текст
            full_text = doc.export_to_markdown()
            
            # Структурированный текст с информацией о разделах
            structured_text = self._build_structured_text(doc)
            
            # Разделы с заголовками
            sections = self._extract_sections(doc)
            
            # Метаданные
            metadata = self._extract_metadata(doc)
            
            logger.info(f"Извлечено {len(sections)} разделов из документа")
            
            return {
                "full_text": full_text,
                "structured_text": structured_text,
                "sections": sections,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Ошибка извлечения структуры: {e}")
            return {
                "full_text": doc.export_to_markdown() if hasattr(doc, 'export_to_markdown') else "",
                "structured_text": "",
                "sections": [],
                "metadata": {}
            }
    
    def _build_structured_text(self, doc: DoclingDocument) -> str:
        """Построение текста с сохранением структуры"""
        try:
            # Docling сохраняет структуру в markdown
            return doc.export_to_markdown()
        except:
            # Fallback: просто полный текст
            try:
                return doc.export_to_text()
            except:
                return ""
    
    def _extract_sections(self, doc: DoclingDocument) -> List[Dict]:
        """Извлечение разделов документа"""
        sections = []
        
        try:
            # Экспортируем в JSON для получения структуры
            json_content = doc.export_to_dict()
            
            # Анализируем структуру
            if isinstance(json_content, dict):
                # Рекурсивно проходим по элементам
                sections = self._parse_json_structure(json_content)
            
        except Exception as e:
            logger.debug(f"Ошибка извлечения разделов: {e}")
        
        return sections
    
    def _parse_json_structure(self, obj: any, level: int = 0, parent_title: str = "") -> List[Dict]:
        """Рекурсивный парсинг структуры JSON"""
        sections = []
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                # Ищем заголовки
                if key in ['heading', 'title', 'section']:
                    if isinstance(value, str):
                        sections.append({
                            "title": value,
                            "level": level,
                            "content": ""
                        })
                elif key in ['content', 'text', 'body']:
                    if isinstance(value, str) and sections:
                        sections[-1]["content"] = value
                
                # Рекурсивно парсим вложенные элементы
                sections.extend(self._parse_json_structure(value, level + 1, parent_title))
        
        elif isinstance(obj, list):
            for item in obj:
                sections.extend(self._parse_json_structure(item, level, parent_title))
        
        return sections
    
    def _extract_metadata(self, doc: DoclingDocument) -> Dict:
        """Извлечение метаданных документа"""
        metadata = {}
        
        try:
            # Получаем доступные метаданные
            if hasattr(doc, 'name'):
                metadata['name'] = doc.name
            
            if hasattr(doc, 'pages'):
                metadata['page_count'] = len(doc.pages)
            
            if hasattr(doc, 'document_origin'):
                metadata['origin'] = str(doc.document_origin)
            
            logger.debug(f"Метаданные: {metadata}")
        except Exception as e:
            logger.debug(f"Ошибка извлечения метаданных: {e}")
        
        return metadata
    
    def documents_to_langchain(self, file_path: str, source_name: Optional[str] = None) -> List[Document]:
        """
        Конвертирование распарсенного документа в LangChain Documents для RAG
        
        Args:
            file_path: Путь к документу
            source_name: Название источника для метаданных
        
        Returns:
            Список LangChain Document объектов
        """
        parsed = self.extract_text_with_structure(file_path)
        documents = []
        
        if not parsed['full_text']:
            logger.warning(f"Не удалось извлечь текст из {file_path}")
            return documents
        
        source = source_name or Path(file_path).stem
        
        # Создаем Document для полного текста
        doc = Document(
            page_content=parsed['full_text'],
            metadata={
                'source': source,
                'file': file_path,
                'type': 'full_text'
            }
        )
        documents.append(doc)
        
        # Создаем Documents для каждого раздела
        for i, section in enumerate(parsed['sections']):
            if section.get('content'):
                doc = Document(
                    page_content=section['content'],
                    metadata={
                        'source': source,
                        'file': file_path,
                        'section': section.get('title', f'Section {i}'),
                        'level': section.get('level', 0),
                        'type': 'section'
                    }
                )
                documents.append(doc)
        
        logger.info(f"Создано {len(documents)} LangChain документов из {file_path}")
        return documents
    
    def batch_parse_documents(self, file_paths: List[str]) -> Dict[str, Optional[DoclingDocument]]:
        """
        Пакетный парсинг документов
        
        Args:
            file_paths: Список путей к документам
        
        Returns:
            Словарь {file_path: DoclingDocument}
        """
        results = {}
        
        for file_path in file_paths:
            try:
                doc = self.parse_document(file_path)
                results[file_path] = doc
            except Exception as e:
                logger.error(f"Ошибка парсинга {file_path}: {e}")
                results[file_path] = None
        
        return results
