import json
import hashlib
import re
from typing import Dict, List, Tuple
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class TemplateManager:
    """Менеджер шаблонов договоров"""
    
    def __init__(self, templates_dir: str):
        self.templates_dir = Path(templates_dir)
        self.templates = {}
        self.template_index = {}
        self.template_stats = {}
        
        self.load_templates()
        self.build_index()
    
    def load_templates(self):
        """Загрузка всех шаблонов из директории"""
        for file_path in self.templates_dir.glob("*"):
            if file_path.suffix.lower() in ['.docx', '.doc', '.txt']:
                try:
                    template_data = self._load_template(file_path)
                    self.templates[file_path.stem] = template_data
                    logger.info(f"Загружен шаблон: {file_path.stem}")
                except Exception as e:
                    logger.error(f"Ошибка загрузки шаблона {file_path}: {e}")
    
    def _load_template(self, file_path: Path) -> Dict:
        """Загрузка отдельного шаблона"""
        # Определяем тип файла и читаем соответствующим образом
        if file_path.suffix.lower() in ['.docx', '.doc']:
            content = self._read_word_file(file_path)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        # Создаем хеш для отслеживания изменений
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        return {
            'name': file_path.stem,
            'file_path': str(file_path),
            'content': content,
            'content_hash': content_hash,
            'size': len(content),
            'created': datetime.fromtimestamp(file_path.stat().st_ctime),
            'modified': datetime.fromtimestamp(file_path.stat().st_mtime),
            'metadata': self._extract_template_metadata(content)
        }
    
    def _read_word_file(self, file_path: Path) -> str:
        """Чтение Word файла с несколькими попытками"""
        content = ""
        
        # Попытка 1: docx2txt для .docx
        if file_path.suffix.lower() == '.docx':
            try:
                import docx2txt
                result = docx2txt.process(str(file_path))
                if result and len(result.strip()) > 0:
                    return result
            except Exception as e:
                logger.debug(f"docx2txt не помог: {e}")
        
        # Попытка 2: python-docx для .docx
        if file_path.suffix.lower() == '.docx':
            try:
                from docx import Document
                doc = Document(file_path)
                content = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
                if content and len(content.strip()) > 0:
                    return content
            except Exception as e:
                logger.debug(f"python-docx не помог: {e}")
        
        # Попытка 3: для .doc используем textract или бинарный парсинг
        if file_path.suffix.lower() == '.doc':
            try:
                import textract
                result = textract.process(str(file_path)).decode('utf-8', errors='ignore')
                if result and len(result.strip()) > 0:
                    return result
            except Exception as e:
                logger.debug(f"textract для .doc не помог: {e}")
        
        # Попытка 4: бинарный фоллбэк для .doc
        try:
            with open(file_path, 'rb') as f:
                binary = f.read()
                # Фильтруем текст: кириллица, ASCII, пробелы, переносы
                text = ''.join(
                    chr(b) if (0xC0 <= b <= 0xFF) or (32 <= b < 127) or b in [10, 13, 9]
                    else ' '
                    for b in binary
                )
                content = ' '.join(text.split())  # Нормализуем пробелы
                if content and len(content.strip()) > 50:
                    return content
        except Exception as e:
            logger.debug(f"Бинарный парсинг не помог: {e}")
        
        logger.warning(f"Не удалось прочитать {file_path.name}")
        return content
    
    def _extract_template_metadata(self, content: str) -> Dict:
        """Извлечение метаданных из шаблона"""
        # Находим основные разделы
        sections = []
        current_section = None
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 100:  # Вероятно заголовок
                # Проверяем, похоже ли на заголовок
                if any(marker in line.lower() for marker in ['раздел', 'глава', 'статья', 'пункт']):
                    if current_section:
                        sections.append(current_section)
                    current_section = line
                elif line.isupper() or line.endswith(':'):  # Возможно заголовок
                    if current_section:
                        sections.append(current_section)
                    current_section = line
        
        if current_section and current_section not in sections:
            sections.append(current_section)
        
        # Извлекаем ключевые поля
        metadata = {
            'sections': sections[:10],  # первые 10 разделов
            'has_parties': bool(re.search(r'сторон[аы]', content, re.IGNORECASE)),
            'has_dates': bool(re.search(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', content)),
            'has_amounts': bool(re.search(r'рубл|сумм|стоимость|цена', content, re.IGNORECASE)),
            'has_signatures': bool(re.search(r'подпис|утвержден', content, re.IGNORECASE)),
            'word_count': len(content.split()),
            'line_count': len(lines)
        }
        
        return metadata
    
    def build_index(self):
        """Построение индекса для быстрого поиска шаблонов"""
        for name, template in self.templates.items():
            # Сохраняем статистику
            self.template_stats[name] = {
                'usage_count': 0,
                'last_used': None,
                'match_confidence': 0.0
            }
    
    def find_best_match(self, text: str) -> Tuple[str, float, Dict]:
        """Поиск наиболее подходящего шаблона для текста (упрощённая версия)"""
        if not self.templates:
            return None, 0.0, {}
        
        # Берём первый непустой шаблон
        for name, template in self.templates.items():
            if template.get('content') and len(template.get('content', '').strip()) > 100:
                return name, 1.0, {'template': name}
        
        return None, 0.0, {}
    
    def get_template_content(self, template_name: str, max_length: int = 2000) -> str:
        """Получение содержимого шаблона с ограничением длины"""
        if template_name in self.templates:
            content = self.templates[template_name]['content']
            return content[:max_length] + "..." if len(content) > max_length else content
        return ""
    
    def get_all_templates(self) -> Dict:
        """Получение информации обо всех шаблонах"""
        return {
            'templates': self.templates,
            'stats': self.template_stats,
            'count': len(self.templates)
        }