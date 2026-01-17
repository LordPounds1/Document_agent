"""
Модуль безопасности для Document Processing Agent.

Содержит функции для:
- Валидации входных данных
- Санитизации пользовательского ввода
- Rate limiting
- Безопасного логирования
"""

import html
import logging
import re
import time
from functools import wraps
from typing import Optional

logger = logging.getLogger(__name__)


# ============ VALIDATION ============

def validate_email(email: str) -> bool:
    """Валидация email адреса.
    
    Args:
        email: Email для проверки
        
    Returns:
        True если email валиден
    """
    if not email or not isinstance(email, str):
        return False
    
    # RFC 5322 simplified pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(pattern, email):
        return False
    
    # Дополнительные проверки
    if len(email) > 254:  # Max email length per RFC
        return False
    
    local_part, domain = email.rsplit('@', 1)
    
    if len(local_part) > 64:  # Max local part length
        return False
    
    # Запрещаем подозрительные символы
    dangerous_chars = ['<', '>', '"', "'", ';', '\\', '|', '`', '$']
    if any(char in email for char in dangerous_chars):
        return False
    
    return True


def validate_password(password: str) -> bool:
    """Базовая валидация пароля.
    
    Args:
        password: Пароль для проверки
        
    Returns:
        True если пароль валиден (не пустой, разумной длины)
    """
    if not password or not isinstance(password, str):
        return False
    
    # App passwords обычно 16 символов, обычные пароли 6+
    if len(password) < 6 or len(password) > 256:
        return False
    
    return True


# ============ SANITIZATION ============

def sanitize_html(text: str, max_length: int = 1000) -> str:
    """Санитизация текста для безопасного отображения в HTML.
    
    Args:
        text: Текст для санитизации
        max_length: Максимальная длина
        
    Returns:
        Безопасный текст
    """
    if not text:
        return ""
    
    # Преобразуем в строку
    text = str(text)
    
    # Ограничиваем длину
    if len(text) > max_length:
        text = text[:max_length] + "..."
    
    # HTML escape
    text = html.escape(text)
    
    # Дополнительно удаляем потенциально опасные паттерны
    dangerous_patterns = [
        r'javascript:',
        r'data:',
        r'vbscript:',
        r'on\w+\s*=',  # onclick, onerror, etc.
    ]
    
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text


def sanitize_filename(filename: str) -> str:
    """Санитизация имени файла для предотвращения path traversal.
    
    Args:
        filename: Имя файла
        
    Returns:
        Безопасное имя файла
    """
    if not filename:
        return "unnamed"
    
    # Убираем путь, оставляем только имя файла
    filename = str(filename)
    filename = filename.replace('\\', '/').split('/')[-1]
    
    # Удаляем опасные символы
    dangerous = ['..', '~', '/', '\\', '\x00', ':', '*', '?', '"', '<', '>', '|']
    for char in dangerous:
        filename = filename.replace(char, '_')
    
    # Ограничиваем длину
    if len(filename) > 200:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:190] + ('.' + ext if ext else '')
    
    return filename or "unnamed"


def mask_sensitive_data(text: str) -> str:
    """Маскирование чувствительных данных в тексте.
    
    Args:
        text: Текст с потенциально чувствительными данными
        
    Returns:
        Текст с замаскированными данными
    """
    if not text:
        return ""
    
    # Маскируем пароли в строках типа "password=xxx"
    text = re.sub(r'(password\s*[=:]\s*)[^\s,\'"]+', r'\1****', text, flags=re.IGNORECASE)
    
    # Маскируем API ключи
    text = re.sub(r'(api[_-]?key\s*[=:]\s*)[^\s,\'"]+', r'\1****', text, flags=re.IGNORECASE)
    
    # Маскируем токены
    text = re.sub(r'(token\s*[=:]\s*)[^\s,\'"]+', r'\1****', text, flags=re.IGNORECASE)
    
    return text


# ============ RATE LIMITING ============

class RateLimiter:
    """Простой rate limiter для защиты от brute-force."""
    
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        """
        Args:
            max_attempts: Максимум попыток в окне
            window_seconds: Размер окна в секундах (по умолчанию 5 минут)
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts: dict = {}  # key -> [(timestamp, ...)]
    
    def is_allowed(self, key: str) -> bool:
        """Проверка, разрешено ли действие.
        
        Args:
            key: Ключ (например, IP или email)
            
        Returns:
            True если действие разрешено
        """
        now = time.time()
        
        # Очищаем старые записи
        if key in self.attempts:
            self.attempts[key] = [
                t for t in self.attempts[key] 
                if now - t < self.window_seconds
            ]
        else:
            self.attempts[key] = []
        
        # Проверяем лимит
        if len(self.attempts[key]) >= self.max_attempts:
            return False
        
        # Добавляем попытку
        self.attempts[key].append(now)
        return True
    
    def get_remaining_time(self, key: str) -> int:
        """Время до сброса лимита.
        
        Args:
            key: Ключ
            
        Returns:
            Секунды до сброса
        """
        if key not in self.attempts or not self.attempts[key]:
            return 0
        
        oldest = min(self.attempts[key])
        remaining = self.window_seconds - (time.time() - oldest)
        return max(0, int(remaining))
    
    def reset(self, key: str):
        """Сброс счётчика для ключа."""
        if key in self.attempts:
            del self.attempts[key]


# Глобальный rate limiter для авторизации
login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=300)


# ============ SECURE LOGGING ============

class SecureFormatter(logging.Formatter):
    """Formatter, который маскирует чувствительные данные."""
    
    def format(self, record):
        # Маскируем message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = mask_sensitive_data(record.msg)
        
        # Маскируем args
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = {k: mask_sensitive_data(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(mask_sensitive_data(str(a)) for a in record.args)
        
        return super().format(record)


def setup_secure_logging(log_file: Optional[str] = None, level: int = logging.INFO):
    """Настройка безопасного логирования.
    
    Args:
        log_file: Путь к файлу логов (опционально)
        level: Уровень логирования
    """
    formatter = SecureFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    handlers = [console_handler]
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=level,
        handlers=handlers
    )


# ============ PASSWORD ENCRYPTION FOR STORAGE ============

import base64
import os
import hashlib

# Ключ шифрования из переменных окружения или генерируется
_ENCRYPTION_KEY = None


def _get_encryption_key() -> bytes:
    """Получение ключа шифрования."""
    global _ENCRYPTION_KEY
    
    if _ENCRYPTION_KEY is None:
        key_env = os.getenv('MONITOR_ENCRYPTION_KEY')
        if key_env:
            _ENCRYPTION_KEY = hashlib.sha256(key_env.encode()).digest()
        else:
            # Генерируем ключ на основе machine-specific данных
            machine_id = os.getenv('HOSTNAME', '') + os.getenv('USER', 'default')
            _ENCRYPTION_KEY = hashlib.sha256(machine_id.encode()).digest()
    
    return _ENCRYPTION_KEY


def encrypt_password(password: str) -> str:
    """Простое шифрование пароля для хранения.
    
    Использует XOR с ключом + base64.
    Не криптостойкое, но достаточное для защиты от случайного просмотра.
    
    Args:
        password: Пароль для шифрования
        
    Returns:
        Зашифрованная строка в base64
    """
    if not password:
        return ''
    
    key = _get_encryption_key()
    password_bytes = password.encode('utf-8')
    
    # XOR шифрование
    encrypted = bytes([
        password_bytes[i] ^ key[i % len(key)]
        for i in range(len(password_bytes))
    ])
    
    return base64.b64encode(encrypted).decode('ascii')


def decrypt_password(encrypted: str) -> str:
    """Расшифровка пароля.
    
    Args:
        encrypted: Зашифрованная строка в base64
        
    Returns:
        Расшифрованный пароль
    """
    if not encrypted:
        return ''
    
    key = _get_encryption_key()
    
    try:
        encrypted_bytes = base64.b64decode(encrypted.encode('ascii'))
        
        # XOR дешифрование (симметричное)
        decrypted = bytes([
            encrypted_bytes[i] ^ key[i % len(key)]
            for i in range(len(encrypted_bytes))
        ])
        
        return decrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to decrypt password: {e}")
        return ''
