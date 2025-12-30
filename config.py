"""Конфигурация приложения Document Processing Agent"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Конфигурация приложения"""
    
    # Пути
    BASE_DIR = Path(__file__).parent
    MODELS_DIR = BASE_DIR / "models"
    TEMPLATES_DIR = BASE_DIR / "templates"
    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = BASE_DIR / "logs"
    
    # LLM настройки
    MODEL_PATH = os.getenv("MODEL_PATH")
    if not MODEL_PATH or MODEL_PATH.lower() == "none":
        # Автоматический поиск модели
        model_files = list(MODELS_DIR.glob("*.gguf")) if MODELS_DIR.exists() else []
        if model_files:
            MODEL_PATH = str(model_files[0])
            logger.info(f"Найдена модель: {MODEL_PATH}")
        else:
            MODEL_PATH = None
    
    MODEL_CONTEXT_SIZE = int(os.getenv("MODEL_CONTEXT_SIZE", 2048))
    MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", 0.1))
    MODEL_N_GPU_LAYERS = int(os.getenv("MODEL_N_GPU_LAYERS", -1))  # -1 = все слои на GPU
    MODEL_MAX_TOKENS = int(os.getenv("MODEL_MAX_TOKENS", 512))
    
    # Excel
    EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH", str(DATA_DIR / "processed_documents.xlsx"))
    
    # Агент
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", 5))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Почтовые провайдеры
    EMAIL_PROVIDERS = {
        'gmail.com': {'imap': 'imap.gmail.com', 'port': 993},
        'googlemail.com': {'imap': 'imap.gmail.com', 'port': 993},
        'yandex.ru': {'imap': 'imap.yandex.ru', 'port': 993},
        'yandex.kz': {'imap': 'imap.yandex.ru', 'port': 993},
        'yandex.com': {'imap': 'imap.yandex.com', 'port': 993},
        'ya.ru': {'imap': 'imap.yandex.ru', 'port': 993},
        'mail.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'inbox.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'list.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'bk.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'outlook.com': {'imap': 'outlook.office365.com', 'port': 993},
        'hotmail.com': {'imap': 'outlook.office365.com', 'port': 993},
    }
    
    @classmethod
    def get_model_path(cls) -> str:
        """Получение пути к модели"""
        if cls.MODEL_PATH:
            return cls.MODEL_PATH
        
        # Поиск в папке models
        if cls.MODELS_DIR.exists():
            model_files = list(cls.MODELS_DIR.glob("*.gguf"))
            if model_files:
                return str(model_files[0])
        
        return None
    
    @classmethod
    def get_email_server(cls, email_address: str) -> dict:
        """Получение настроек IMAP сервера по email"""
        if not email_address or '@' not in email_address:
            return {'imap': 'imap.gmail.com', 'port': 993}
        
        domain = email_address.split('@')[-1].lower()
        
        if domain in cls.EMAIL_PROVIDERS:
            return cls.EMAIL_PROVIDERS[domain]
        
        # Для Яндекса с разными доменами
        if 'yandex' in domain:
            return {'imap': 'imap.yandex.ru', 'port': 993}
        
        # По умолчанию пробуем imap.domain
        return {'imap': f'imap.{domain}', 'port': 993}


# Создаём директории при необходимости
Config.DATA_DIR.mkdir(exist_ok=True)
Config.LOGS_DIR.mkdir(exist_ok=True)
