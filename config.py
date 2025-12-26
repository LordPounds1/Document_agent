import os
import re
import docx
import docx2txt
import unicodedata
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def clean_password(password):
    """Очистка пароля от невидимых символов и пробелов"""
    if not password:
        return password
    # Удаляем все пробелы (обычные и неразрывные)
    password = password.replace(' ', '').replace('\u00A0', '').replace('\u2009', '')
    # Удаляем символы табуляции и переноса строки
    password = password.replace('\t', '').replace('\n', '').replace('\r', '')
    # Удаляем другие невидимые символы
    password = ''.join(char for char in password if unicodedata.category(char)[0] != 'C' or char.isprintable())
    return password.strip()

class Config:
    """Конфигурация приложения"""
    
    # Пути
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / "data"
    MODELS_DIR = BASE_DIR / "models"
    TEMPLATES_DIR = BASE_DIR / "templates"
    LOGS_DIR = BASE_DIR / "data" / "logs"
    
    # Почта IMAP (получение)
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "").strip() if os.getenv("EMAIL_ADDRESS") else None
    _raw_password = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_PASSWORD = clean_password(_raw_password) if _raw_password else None
    IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
    IMAP_PORT = int(os.getenv("IMAP_PORT", 993))
    USE_SSL = os.getenv("USE_SSL", "true").lower() == "true"
    
    # Дополнительные настройки почты
    EMAIL_FOLDER = os.getenv("EMAIL_FOLDER", "INBOX")  # Папка для мониторинга
    
    # LLM настройки - локальная модель
    # Локальная модель (основной режим)
    MODEL_PATH = os.getenv("MODEL_PATH")
    if not MODEL_PATH or MODEL_PATH.lower() == "none":
        # Автоматический поиск модели в папке models/
        model_files = list(MODELS_DIR.glob("*.gguf"))
        if model_files:
            MODEL_PATH = str(model_files[0])
            logger.info(f"Автоматически найдена модель: {MODEL_PATH}")
        else:
            MODEL_PATH = None
    elif MODEL_PATH and not Path(MODEL_PATH).exists():
        logger.warning(f"Указанный путь к модели не существует: {MODEL_PATH}")
        # Пробуем найти в папке models/
        model_files = list(MODELS_DIR.glob("*.gguf"))
        if model_files:
            MODEL_PATH = str(model_files[0])
            logger.info(f"Используется найденная модель: {MODEL_PATH}")
        else:
            MODEL_PATH = None
    
    MODEL_TYPE = os.getenv("MODEL_TYPE", "gguf")
    MODEL_CONTEXT_SIZE = int(os.getenv("MODEL_CONTEXT_SIZE", 4096))
    MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", 0.1))
    
    # Excel
    EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH", str(DATA_DIR / "processed_documents.xlsx"))
    EXCEL_SHEET_NAME = os.getenv("EXCEL_SHEET_NAME", "Документы")
    
    # Агент
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", 5))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
    
    # Шаблоны - загружаем из папки templates/
    TEMPLATES = {}
    if TEMPLATES_DIR.exists():
        from agents.template_manager import TemplateManager
        try:
            template_manager = TemplateManager(str(TEMPLATES_DIR))
            TEMPLATES = template_manager.templates
            if TEMPLATES:
                logger.info(f"Загружено шаблонов: {len(TEMPLATES)}")
            else:
                logger.warning(f"Папка templates/ существует, но шаблоны не найдены")
        except Exception as e:
            logger.warning(f"Ошибка загрузки шаблонов: {e}")
    
    # Популярные почтовые сервисы (для автоопределения)
    EMAIL_PROVIDERS = {
        'gmail.com': {
            'imap': 'imap.gmail.com',
            'smtp': 'smtp.gmail.com',
            'port': 993,
            'requires_app_password': True
        },
        'yandex.ru': {
            'imap': 'imap.yandex.ru',
            'smtp': 'smtp.yandex.ru',
            'port': 993,
            'requires_app_password': True
        },
        'yandex.kz': {
            'imap': 'imap.yandex.ru',  # Важно: для yandex.kz тоже используется imap.yandex.ru!
            'smtp': 'smtp.yandex.ru',
            'port': 993,
            'requires_app_password': True
        },
        'yandex.ua': {
            'imap': 'imap.yandex.ru',
            'smtp': 'smtp.yandex.ru',
            'port': 993,
            'requires_app_password': True
        },
        'yandex.by': {
            'imap': 'imap.yandex.ru',
            'smtp': 'smtp.yandex.ru',
            'port': 993,
            'requires_app_password': True
        },
        'mail.ru': {
            'imap': 'imap.mail.ru',
            'smtp': 'smtp.mail.ru',
            'port': 993,
            'requires_app_password': False
        },
        'rambler.ru': {
            'imap': 'imap.rambler.ru',
            'smtp': 'smtp.rambler.ru',
            'port': 993,
            'requires_app_password': False
        },
        'outlook.com': {
            'imap': 'outlook.office365.com',
            'smtp': 'smtp.office365.com',
            'port': 993,
            'requires_app_password': False
        },
        'hotmail.com': {
            'imap': 'outlook.office365.com',
            'smtp': 'smtp.office365.com',
            'port': 993,
            'requires_app_password': False
        },
        'yahoo.com': {
            'imap': 'imap.mail.yahoo.com',
            'smtp': 'smtp.mail.yahoo.com',
            'port': 993,
            'requires_app_password': True
        }
    }
    
    @classmethod
    def detect_email_provider(cls, email_address: str) -> dict:
        """Определение почтового провайдера по email адресу"""
        if not email_address or '@' not in email_address:
            return {
                'imap': cls.IMAP_SERVER,
                'smtp': 'smtp.gmail.com',
                'port': cls.IMAP_PORT,
                'requires_app_password': False
            }
        
        domain = email_address.split('@')[-1].lower()
        
        # Сначала ищем точное совпадение
        if domain in cls.EMAIL_PROVIDERS:
            return cls.EMAIL_PROVIDERS[domain]
        
        # Ищем частичное совпадение для субдоменов
        for provider_domain, config in cls.EMAIL_PROVIDERS.items():
            if domain.endswith('.' + provider_domain):
                return config
        
        # Для Яндекса: yandex.kz, yandex.ua и т.д.
        if 'yandex' in domain:
            # Все домены Яндекса используют imap.yandex.ru
            return {
                'imap': 'imap.yandex.ru',
                'smtp': 'smtp.yandex.ru',
                'port': 993,
                'requires_app_password': True
            }
        
        # Возвращаем настройки по умолчанию
        return {
            'imap': cls.IMAP_SERVER,
            'smtp': 'smtp.gmail.com',
            'port': cls.IMAP_PORT,
            'requires_app_password': False
        }