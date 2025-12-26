import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logger(level: str = "INFO"):
    """Настройка логирования"""
    
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Логгер
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Удаляем существующие handlers (если есть)
    logger.handlers.clear()
    
    # Консольный handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)
    
    # Файловый handler
    log_file = Path("./data/logs") / f"agent_{datetime.now().strftime('%Y%m%d')}.log"
    log_file.parent.mkdir(exist_ok=True, parents=True)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # В файл пишем все
    logger.addHandler(file_handler)
    
    return logger