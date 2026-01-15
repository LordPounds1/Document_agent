"""Tests for config.py."""

import os
from pathlib import Path

import pytest


class TestConfig:
    """Тесты для класса Config."""

    def test_config_imports(self):
        """Проверка успешного импорта конфигурации."""
        from config import Config
        assert Config is not None

    def test_base_dir_exists(self):
        """Проверка что BASE_DIR указывает на существующую директорию."""
        from config import Config
        assert Config.BASE_DIR.exists()

    def test_directories_created(self):
        """Проверка создания необходимых директорий."""
        from config import Config
        assert Config.DATA_DIR.exists()
        assert Config.LOGS_DIR.exists()

    def test_model_context_size_is_positive(self):
        """Проверка что размер контекста положительный."""
        from config import Config
        assert Config.MODEL_CONTEXT_SIZE > 0

    def test_model_temperature_in_range(self):
        """Проверка что температура в допустимом диапазоне."""
        from config import Config
        assert 0.0 <= Config.MODEL_TEMPERATURE <= 2.0

    def test_email_providers_not_empty(self):
        """Проверка наличия email провайдеров."""
        from config import Config
        assert len(Config.EMAIL_PROVIDERS) > 0

    def test_get_email_server_gmail(self):
        """Проверка получения настроек Gmail."""
        from config import Config
        settings = Config.get_email_server("test@gmail.com")
        assert settings['imap'] == 'imap.gmail.com'
        assert settings['port'] == 993

    def test_get_email_server_yandex(self):
        """Проверка получения настроек Yandex."""
        from config import Config
        settings = Config.get_email_server("test@yandex.ru")
        assert settings['imap'] == 'imap.yandex.ru'
        assert settings['port'] == 993

    def test_get_email_server_unknown_domain(self):
        """Проверка fallback для неизвестного домена."""
        from config import Config
        settings = Config.get_email_server("test@unknown-domain.com")
        assert 'imap' in settings
        assert settings['port'] == 993

    def test_get_email_server_invalid_email(self):
        """Проверка обработки невалидного email."""
        from config import Config
        settings = Config.get_email_server("invalid-email")
        assert 'imap' in settings

    def test_get_model_path_returns_string_or_none(self):
        """Проверка что get_model_path возвращает строку или None."""
        from config import Config
        path = Config.get_model_path()
        assert path is None or isinstance(path, str)
