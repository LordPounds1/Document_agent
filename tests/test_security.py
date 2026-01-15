"""
Тесты для модуля безопасности.
"""

import pytest
from utils.security import (
    validate_email,
    validate_password,
    sanitize_html,
    sanitize_filename,
    mask_sensitive_data,
    RateLimiter,
)


class TestValidateEmail:
    """Тесты валидации email."""
    
    def test_valid_emails(self):
        """Проверка валидных email адресов."""
        valid_emails = [
            "user@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user@subdomain.example.com",
            "user123@example.co.uk",
        ]
        for email in valid_emails:
            assert validate_email(email) is True, f"Should be valid: {email}"
    
    def test_invalid_emails(self):
        """Проверка невалидных email адресов."""
        invalid_emails = [
            "",
            None,
            "not-an-email",
            "@example.com",
            "user@",
            "user@.com",
            "user@example",
            "user space@example.com",
            "user<script>@example.com",  # XSS attempt
            "user'--@example.com",  # SQL injection attempt
        ]
        for email in invalid_emails:
            assert validate_email(email) is False, f"Should be invalid: {email}"
    
    def test_email_too_long(self):
        """Email слишком длинный."""
        long_email = "a" * 250 + "@example.com"
        assert validate_email(long_email) is False


class TestValidatePassword:
    """Тесты валидации пароля."""
    
    def test_valid_passwords(self):
        """Проверка валидных паролей."""
        valid_passwords = [
            "password123",
            "MySecureP@ss",
            "a" * 100,
            "12345678",
        ]
        for pwd in valid_passwords:
            assert validate_password(pwd) is True, f"Should be valid: {pwd}"
    
    def test_invalid_passwords(self):
        """Проверка невалидных паролей."""
        invalid_passwords = [
            "",
            None,
            "short",  # Меньше 6 символов
            "a" * 300,  # Слишком длинный
        ]
        for pwd in invalid_passwords:
            assert validate_password(pwd) is False, f"Should be invalid: {pwd}"


class TestSanitizeHtml:
    """Тесты санитизации HTML."""
    
    def test_basic_escape(self):
        """Базовое экранирование HTML."""
        assert "&lt;" in sanitize_html("<script>")
        assert "&gt;" in sanitize_html("</script>")
        assert "&amp;" in sanitize_html("&")
    
    def test_xss_prevention(self):
        """Предотвращение XSS атак."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img onerror='alert(1)'>",
            "<div onclick='alert(1)'>",
        ]
        for payload in xss_payloads:
            sanitized = sanitize_html(payload)
            assert "javascript:" not in sanitized.lower()
            assert "onerror" not in sanitized.lower()
            assert "onclick" not in sanitized.lower()
    
    def test_max_length(self):
        """Ограничение длины."""
        long_text = "a" * 2000
        result = sanitize_html(long_text, max_length=100)
        assert len(result) <= 103  # 100 + "..."
    
    def test_empty_input(self):
        """Пустой ввод."""
        assert sanitize_html("") == ""
        assert sanitize_html(None) == ""


class TestSanitizeFilename:
    """Тесты санитизации имён файлов."""
    
    def test_path_traversal(self):
        """Предотвращение path traversal."""
        dangerous_names = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "file/../../../secret.txt",
        ]
        for name in dangerous_names:
            sanitized = sanitize_filename(name)
            assert ".." not in sanitized
            assert "/" not in sanitized
            assert "\\" not in sanitized
    
    def test_null_byte(self):
        """Удаление null bytes."""
        assert "\x00" not in sanitize_filename("file\x00.txt")
    
    def test_special_characters(self):
        """Удаление специальных символов."""
        assert ":" not in sanitize_filename("file:name.txt")
        assert "*" not in sanitize_filename("file*.txt")
        assert "?" not in sanitize_filename("file?.txt")
    
    def test_empty_input(self):
        """Пустой ввод."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename(None) == "unnamed"


class TestMaskSensitiveData:
    """Тесты маскирования чувствительных данных."""
    
    def test_password_masking(self):
        """Маскирование паролей."""
        text = "password=mysecretpass123"
        masked = mask_sensitive_data(text)
        assert "mysecretpass123" not in masked
        assert "****" in masked
    
    def test_api_key_masking(self):
        """Маскирование API ключей."""
        text = "api_key=sk-1234567890abcdef"
        masked = mask_sensitive_data(text)
        assert "sk-1234567890abcdef" not in masked
    
    def test_token_masking(self):
        """Маскирование токенов."""
        text = "token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked = mask_sensitive_data(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in masked
    
    def test_regular_text_unchanged(self):
        """Обычный текст не меняется."""
        text = "This is a regular log message"
        assert mask_sensitive_data(text) == text


class TestRateLimiter:
    """Тесты rate limiter."""
    
    def test_allows_within_limit(self):
        """Разрешает запросы в пределах лимита."""
        limiter = RateLimiter(max_attempts=3, window_seconds=60)
        
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
    
    def test_blocks_over_limit(self):
        """Блокирует после превышения лимита."""
        limiter = RateLimiter(max_attempts=2, window_seconds=60)
        
        assert limiter.is_allowed("user2") is True
        assert limiter.is_allowed("user2") is True
        assert limiter.is_allowed("user2") is False  # Третья попытка заблокирована
    
    def test_different_keys_independent(self):
        """Разные ключи независимы."""
        limiter = RateLimiter(max_attempts=1, window_seconds=60)
        
        assert limiter.is_allowed("user3") is True
        assert limiter.is_allowed("user3") is False
        assert limiter.is_allowed("user4") is True  # Другой пользователь
    
    def test_reset(self):
        """Сброс счётчика."""
        limiter = RateLimiter(max_attempts=1, window_seconds=60)
        
        limiter.is_allowed("user5")
        assert limiter.is_allowed("user5") is False
        
        limiter.reset("user5")
        assert limiter.is_allowed("user5") is True
