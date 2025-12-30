"""Настройка логирования с поддержкой Unicode для Windows"""

import logging
import sys
from pathlib import Path


class UnicodeStreamHandler(logging.StreamHandler):
    """StreamHandler с принудительной UTF-8 кодировкой для Windows"""
    
    def __init__(self, stream=None):
        super().__init__(stream)
        # Принудительно используем UTF-8 для вывода
        if stream is None:
            stream = sys.stderr
        
        # Для Windows: оборачиваем stream в UTF-8 writer
        if hasattr(stream, 'buffer'):
            import io
            self.stream = io.TextIOWrapper(
                stream.buffer,
                encoding='utf-8',
                errors='replace',  # Заменяем проблемные символы
                line_buffering=True
            )
        else:
            self.stream = stream


def setup_logger(log_level: str = "INFO"):
    """
    Настройка логирования с поддержкой Unicode
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
    """
    # Создаем директорию для логов
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Удаляем существующие handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Устанавливаем уровень
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)
    
    # Формат логов БЕЗ эмодзи
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(
        log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler с UTF-8 поддержкой
    console_handler = UnicodeStreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler с UTF-8 кодировкой
    file_handler = logging.FileHandler(
        log_dir / "app.log",
        encoding='utf-8',
        mode='a'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Тестовое сообщение
    root_logger.info("Logger initialized with UTF-8 support")
    
    return root_logger