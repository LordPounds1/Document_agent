"""Упрощённый процессор документов с LLM."""

from datetime import datetime
from typing import Any
import logging
import re

from config import Config
from core.llm import LLMClient
from core.rag import SimpleRAG
logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Процессор документов для извлечения информации из договоров"""

    def __init__(self, model_path: str, templates_dir: str = "templates",
                 enable_learning: bool | None = None):
        """
        Args:
            model_path: Путь к GGUF модели
            templates_dir: Директория с шаблонами договоров
            enable_learning: Включить автоматическое обучение (если None - берётся из Config)
        """
        self.model_path = model_path
        self.llm = None
        self.rag = None

        # Ленивая инициализация
        self._llm_initialized = False
        self._rag_initialized = False
        self.templates_dir = templates_dir

        # Настройки обучения
        self.enable_learning = enable_learning if enable_learning is not None else Config.RAG_ENABLE_LEARNING

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
            self.rag = SimpleRAG(
                templates_dir=self.templates_dir,
                persist_dir=Config.RAG_PERSIST_DIR,
                use_gpu=Config.RAG_USE_GPU,
                enable_learning=self.enable_learning
            )
            self._rag_initialized = True
            logger.info(f"✅ RAG initialized (learning: {self.enable_learning})")
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

    def extract_contract_info(self, text: str) -> dict[str, Any]:
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
            - execution_period: Срок исполнения обязательства
            - penalties: Ответственность (пени, неустойки, штрафы)
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
СРОК_ДЕЙСТВИЯ: [срок действия договора]
СРОК_ИСПОЛНЕНИЯ: [срок исполнения обязательства - когда должны выполнить работу/поставить товар/оказать услугу]
ОТВЕТСТВЕННОСТЬ: [пени, неустойки, штрафы за нарушение - размер в % или сумма]
ОТВЕТСТВЕННЫЕ_ЛИЦА: [ФИО ответственных лиц]
ОПИСАНИЕ: [краткое описание договора в 1-2 предложения, включая ключевые условия]

Ответ:"""

        try:
            response = self.llm.generate(prompt, max_tokens=512, temperature=0.1)
            return self._parse_llm_response(response, text)
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return self._extract_basic_info(text)

    def _parse_llm_response(self, response: str, original_text: str) -> dict[str, Any]:
        """Парсинг ответа LLM"""
        result = {
            'document_type': 'Договор',
            'parties': '',
            'subject': '',
            'amount': '',
            'date': '',
            'deadline': '',
            'execution_period': '',
            'penalties': '',
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
            'deadline': r'СРОК_ДЕЙСТВИЯ:\s*(.+?)(?:\n|$)',
            'execution_period': r'СРОК_ИСПОЛНЕНИЯ:\s*(.+?)(?:\n|$)',
            'penalties': r'ОТВЕТСТВЕННОСТЬ:\s*(.+?)(?:\n|$)',
            'responsible': r'ОТВЕТСТВЕННЫЕ_ЛИЦА:\s*(.+?)(?:\n|$)',
            'summary': r'ОПИСАНИЕ:\s*(.+?)(?:\n|$)',
        }

        for field, pattern in patterns.items():
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and value.lower() not in ['не указано', 'нет', '-', 'n/a', 'не найдено']:
                    result[field] = value

        # Если summary пустой, берём первые 100 символов
        if not result['summary']:
            result['summary'] = original_text[:100].replace('\n', ' ').strip() + '...'

        # Дополняем summary информацией о пенях и сроках исполнения если есть
        summary_additions = []
        if result['execution_period']:
            summary_additions.append(f"Срок исполнения: {result['execution_period']}")
        if result['penalties']:
            summary_additions.append(f"Ответственность: {result['penalties']}")

        if summary_additions and result['summary']:
            result['summary'] = result['summary'].rstrip('.') + '. ' + '. '.join(summary_additions) + '.'

        return result

    def _extract_basic_info(self, text: str) -> dict[str, Any]:
        """Базовое извлечение без LLM (fallback)"""
        result = {
            'document_type': 'Договор',
            'parties': '',
            'subject': '',
            'amount': '',
            'date': '',
            'deadline': '',
            'execution_period': '',
            'penalties': '',
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

        # Поиск пени/неустойки/штрафов
        penalties_patterns = [
            r'(?:пеня|пени)\s*(?:в размере)?\s*([\d,\.]+\s*%[^.]*)',
            r'(?:неустойка|неустойку)\s*(?:в размере)?\s*([\d,\.]+\s*%[^.]*)',
            r'(?:штраф|штрафа?)\s*(?:в размере)?\s*([\d,\.]+\s*%[^.]*)',
            r'([\d,\.]+\s*%\s*(?:за каждый день|от суммы)[^.]*)',
        ]
        for pattern in penalties_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['penalties'] = match.group(1).strip()
                break

        # Поиск срока исполнения
        execution_patterns = [
            r'(?:срок\s+исполнения|выполнить\s+в\s+срок|в\s+течение)\s*[:—-]?\s*([^.]+?)(?:\.|$)',
            r'(?:поставить|выполнить|оказать)\s+(?:в\s+срок\s+)?до\s+([^.]+?)(?:\.|$)',
            r'(?:не\s+позднее)\s+([^.]+?)(?:\.|$)',
        ]
        for pattern in execution_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['execution_period'] = match.group(1).strip()[:100]
                break

        return result

    def process_email_with_contract(self, email_data: dict,
                                    contract_text: str,
                                    auto_learn: bool = True) -> dict[str, Any]:
        """Обработка email с договором

        Args:
            email_data: Данные письма
            contract_text: Текст договора (из тела или вложения)
            auto_learn: Автоматически обучить RAG на этом договоре

        Returns:
            Полная информация для записи в Excel
        """
        # Извлекаем информацию из договора
        contract_info = self.extract_contract_info(contract_text)

        # Автоматическое обучение RAG на новом договоре
        learning_result = None
        if auto_learn and self.rag:
            # Извлекаем стороны из текста для метаданных
            parties = []
            if contract_info.get('parties'):
                parties = [p.strip() for p in contract_info['parties'].split(',')]

            learning_result = self.rag.learn_from_document(
                content=contract_text,
                document_type=contract_info.get('document_type', 'unknown'),
                source='email',
                parties=parties
            )

            if learning_result.get('success'):
                logger.info(f"📚 RAG обучился на договоре: {contract_info.get('document_type')}")
            else:
                logger.debug(f"RAG не обучился: {learning_result.get('message')}")

        # Формируем результат для Excel
        result = {
            'email_id': email_data.get('id', ''),
            'email_from': email_data.get('from', ''),
            'email_subject': email_data.get('subject', ''),
            'email_date': email_data.get('date', datetime.now()),
            'document_type': contract_info['document_type'],
            'summary': contract_info['summary'],
            'parties': contract_info['parties'],
            'amount': contract_info['amount'],
            'responsible': contract_info['responsible'],
            'processed_at': contract_info['processed_at'],
            'learned': learning_result.get('success', False) if learning_result else False
        }

        return result

    def process_document(self, text: str, source: str = "manual",
                        auto_learn: bool = True) -> dict[str, Any]:
        """Универсальная обработка документа с автоматическим обучением.

        Args:
            text: Текст документа
            source: Источник (manual, file, email)
            auto_learn: Автоматически обучить RAG

        Returns:
            Результат обработки с информацией об обучении
        """
        # Проверяем, является ли это договором
        is_contract, confidence = self.is_contract(text)

        if not is_contract:
            return {
                'success': False,
                'is_contract': False,
                'confidence': confidence,
                'message': 'Документ не является договором'
            }

        # Извлекаем информацию
        contract_info = self.extract_contract_info(text)

        # Обучение RAG
        learning_result = None
        if auto_learn:
            self._init_rag()
            if self.rag:
                parties = []
                if contract_info.get('parties'):
                    parties = [p.strip() for p in contract_info['parties'].split(',')]

                learning_result = self.rag.learn_from_document(
                    content=text,
                    document_type=contract_info.get('document_type', 'unknown'),
                    source=source,
                    parties=parties
                )

        return {
            'success': True,
            'is_contract': True,
            'confidence': confidence,
            'contract_info': contract_info,
            'learning': learning_result,
            'message': 'Документ успешно обработан'
        }

    def get_learning_stats(self) -> dict[str, Any]:
        """Получение статистики обучения RAG."""
        self._init_rag()
        if self.rag:
            return self.rag.get_learning_stats()
        return {'error': 'RAG не инициализирован'}

    def close(self):
        """Освобождение ресурсов"""
        if self.llm:
            self.llm.close()
            self.llm = None
            self._llm_initialized = False

