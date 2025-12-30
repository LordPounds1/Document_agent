"""Упрощённый процессор документов с LLM"""

import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime

from core.llm import LLMClient
from core.rag import SimpleRAG

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Процессор документов для извлечения информации из договоров"""
    
    def __init__(self, model_path: str, templates_dir: str = "templates"):
        """
        Args:
            model_path: Путь к GGUF модели
            templates_dir: Директория с шаблонами договоров
        """
        self.model_path = model_path
        self.llm = None
        self.rag = None
        
        # Ленивая инициализация
        self._llm_initialized = False
        self._rag_initialized = False
        self.templates_dir = templates_dir
    
    def _init_llm(self):
        """Инициализация LLM"""
        if self._llm_initialized:
            return
        
        try:
            self.llm = LLMClient(self.model_path, n_ctx=2048, n_gpu_layers=-1)
            self._llm_initialized = True
            logger.info("✅ LLM initialized")
        except Exception as e:
            logger.error(f"❌ LLM init failed: {e}")
            self.llm = None
    
    def _init_rag(self):
        """Инициализация RAG"""
        if self._rag_initialized:
            return
        
        try:
            self.rag = SimpleRAG(templates_dir=self.templates_dir)
            self._rag_initialized = True
            logger.info("✅ RAG initialized")
        except Exception as e:
            logger.error(f"❌ RAG init failed: {e}")
            self.rag = None
    
    def is_contract(self, text: str) -> tuple:
        """Проверка, является ли текст договором
        
        Returns:
            (is_contract, confidence)
        """
        self._init_rag()
        if self.rag:
            return self.rag.is_contract(text)
        
        # Fallback - простой поиск по ключевым словам
        keywords = ['договор', 'контракт', 'соглашение', 'стороны', 'обязуется']
        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw in text_lower)
        confidence = min(1.0, matches / 3)
        return confidence >= 0.5, confidence
    
    def extract_contract_info(self, text: str) -> Dict[str, Any]:
        """Извлечение информации из договора с помощью LLM
        
        Args:
            text: Текст договора
            
        Returns:
            Словарь с извлечённой информацией:
            - document_type: Тип документа
            - parties: Стороны договора
            - subject: Предмет договора
            - amount: Сумма
            - date: Дата договора
            - deadline: Срок действия
            - responsible: Ответственные лица
            - summary: Краткое описание
        """
        self._init_llm()
        
        if not self.llm:
            return self._extract_basic_info(text)
        
        # Ограничиваем текст для контекста LLM
        text_truncated = text[:3000] if len(text) > 3000 else text
        
        prompt = f"""Ты - юридический ассистент. Проанализируй договор и извлеки информацию.

ДОГОВОР:
{text_truncated}

Извлеки следующую информацию и верни в формате:
ТИП: [тип договора]
СТОРОНЫ: [кто является сторонами]
ПРЕДМЕТ: [предмет договора]
СУММА: [сумма если есть]
ДАТА: [дата договора]
СРОК: [срок действия]
ОТВЕТСТВЕННЫЕ: [ФИО ответственных лиц]
ОПИСАНИЕ: [краткое описание в 1-2 предложения]

Ответ:"""

        try:
            response = self.llm.generate(prompt, max_tokens=512, temperature=0.1)
            return self._parse_llm_response(response, text)
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return self._extract_basic_info(text)
    
    def _parse_llm_response(self, response: str, original_text: str) -> Dict[str, Any]:
        """Парсинг ответа LLM"""
        result = {
            'document_type': 'Договор',
            'parties': '',
            'subject': '',
            'amount': '',
            'date': '',
            'deadline': '',
            'responsible': '',
            'summary': '',
            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Парсим каждое поле
        patterns = {
            'document_type': r'ТИП:\s*(.+?)(?:\n|$)',
            'parties': r'СТОРОНЫ:\s*(.+?)(?:\n|$)',
            'subject': r'ПРЕДМЕТ:\s*(.+?)(?:\n|$)',
            'amount': r'СУММА:\s*(.+?)(?:\n|$)',
            'date': r'ДАТА:\s*(.+?)(?:\n|$)',
            'deadline': r'СРОК:\s*(.+?)(?:\n|$)',
            'responsible': r'ОТВЕТСТВЕННЫЕ:\s*(.+?)(?:\n|$)',
            'summary': r'ОПИСАНИЕ:\s*(.+?)(?:\n|$)',
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and value.lower() not in ['не указано', 'нет', '-', 'n/a']:
                    result[field] = value
        
        # Если summary пустой, берём первые 100 символов
        if not result['summary']:
            result['summary'] = original_text[:100].replace('\n', ' ').strip() + '...'
        
        return result
    
    def _extract_basic_info(self, text: str) -> Dict[str, Any]:
        """Базовое извлечение без LLM (fallback)"""
        result = {
            'document_type': 'Договор',
            'parties': '',
            'subject': '',
            'amount': '',
            'date': '',
            'deadline': '',
            'responsible': '',
            'summary': text[:150].replace('\n', ' ').strip() + '...',
            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        text_lower = text.lower()
        
        # Определение типа
        if 'аренд' in text_lower:
            result['document_type'] = 'Договор аренды'
        elif 'поставк' in text_lower:
            result['document_type'] = 'Договор поставки'
        elif 'подряд' in text_lower:
            result['document_type'] = 'Договор подряда'
        elif 'услуг' in text_lower:
            result['document_type'] = 'Договор оказания услуг'
        elif 'купл' in text_lower and 'продаж' in text_lower:
            result['document_type'] = 'Договор купли-продажи'
        
        # Поиск суммы (простой паттерн)
        amount_match = re.search(r'(\d[\d\s]*(?:тенге|тг|руб|рублей|₽|₸))', text, re.IGNORECASE)
        if amount_match:
            result['amount'] = amount_match.group(1).strip()
        
        # Поиск даты
        date_match = re.search(r'(\d{1,2}[./]\d{1,2}[./]\d{2,4})', text)
        if date_match:
            result['date'] = date_match.group(1)
        
        return result
    
    def process_email_with_contract(self, email_data: Dict, 
                                    contract_text: str) -> Dict[str, Any]:
        """Обработка email с договором
        
        Args:
            email_data: Данные письма
            contract_text: Текст договора (из тела или вложения)
            
        Returns:
            Полная информация для записи в Excel
        """
        # Извлекаем информацию из договора
        contract_info = self.extract_contract_info(contract_text)
        
        # Формируем результат для Excel
        return {
            'email_id': email_data.get('id', ''),
            'email_from': email_data.get('from', ''),
            'email_subject': email_data.get('subject', ''),
            'email_date': email_data.get('date', datetime.now()),
            'document_type': contract_info['document_type'],
            'summary': contract_info['summary'],
            'parties': contract_info['parties'],
            'amount': contract_info['amount'],
            'responsible': contract_info['responsible'],
            'processed_at': contract_info['processed_at']
        }
    
    def close(self):
        """Освобождение ресурсов"""
        if self.llm:
            self.llm.close()
            self.llm = None
            self._llm_initialized = False
