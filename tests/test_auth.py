"""
Тесты для модуля аутентификации.
"""

import sys

import pytest
from unittest.mock import MagicMock
# Mock streamlit before importing auth
mock_st = MagicMock()
mock_st.session_state = {}
sys.modules['streamlit'] = mock_st

from utils.auth import (
    _hash_password,
    _verify_password,
    _load_users,
    _save_user,
    authenticate,
    check_first_run,
)


class TestPasswordHashing:
    """Тесты хэширования паролей."""

    def test_hash_produces_hex_strings(self):
        """Хэш и соль - hex строки."""
        hash_val, salt = _hash_password("testpassword")

        # Проверяем что это hex строки
        assert isinstance(hash_val, str)
        assert isinstance(salt, str)
        bytes.fromhex(hash_val)  # Должно работать без ошибок
        bytes.fromhex(salt)

    def test_same_password_different_salt(self):
        """Один и тот же пароль с разной солью даёт разные хэши."""
        hash1, salt1 = _hash_password("password")
        hash2, salt2 = _hash_password("password")

        assert hash1 != hash2  # Разные хэши из-за разной соли
        assert salt1 != salt2

    def test_same_password_same_salt(self):
        """Один пароль с одинаковой солью даёт одинаковый хэш."""
        _, salt = _hash_password("password")

        hash1, _ = _hash_password("password", salt)
        hash2, _ = _hash_password("password", salt)

        assert hash1 == hash2

    def test_verify_correct_password(self):
        """Верификация правильного пароля."""
        password = "correctpassword"
        hash_val, salt = _hash_password(password)

        assert _verify_password(password, hash_val, salt) is True

    def test_verify_wrong_password(self):
        """Верификация неправильного пароля."""
        password = "correctpassword"
        hash_val, salt = _hash_password(password)

        assert _verify_password("wrongpassword", hash_val, salt) is False

    def test_hash_is_deterministic_with_salt(self):
        """Хэширование детерминировано при фиксированной соли."""
        salt = "a" * 64  # 32 bytes in hex

        hash1, _ = _hash_password("test", salt)
        hash2, _ = _hash_password("test", salt)

        assert hash1 == hash2


class TestUserManagement:
    """Тесты управления пользователями."""

    @pytest.fixture
    def temp_users_file(self, tmp_path, monkeypatch):
        """Временный файл пользователей."""
        users_file = tmp_path / ".users"
        monkeypatch.setattr("utils.auth.USERS_FILE", users_file)
        return users_file

    def test_check_first_run_no_file(self, temp_users_file):
        """Первый запуск - файла нет."""
        assert check_first_run() is True

    def test_check_first_run_empty_file(self, temp_users_file):
        """Первый запуск - пустой файл."""
        temp_users_file.write_text("")
        assert check_first_run() is True

    def test_check_first_run_has_users(self, temp_users_file):
        """Не первый запуск - есть пользователи."""
        temp_users_file.write_text("admin:hash:salt\n")
        assert check_first_run() is False

    def test_save_and_load_user(self, temp_users_file):
        """Сохранение и загрузка пользователя."""
        _save_user("testuser", "testpass")

        users = _load_users()
        assert "testuser" in users
        assert "hash" in users["testuser"]
        assert "salt" in users["testuser"]

    def test_authenticate_valid_user(self, temp_users_file):
        """Аутентификация валидного пользователя."""
        _save_user("validuser", "validpass")

        assert authenticate("validuser", "validpass") is True

    def test_authenticate_wrong_password(self, temp_users_file):
        """Аутентификация с неправильным паролем."""
        _save_user("user", "correctpass")

        assert authenticate("user", "wrongpass") is False

    def test_authenticate_nonexistent_user(self, temp_users_file):
        """Аутентификация несуществующего пользователя."""
        assert authenticate("nonexistent", "anypass") is False

    def test_multiple_users(self, temp_users_file):
        """Несколько пользователей."""
        _save_user("user1", "pass1")
        _save_user("user2", "pass2")

        users = _load_users()
        assert len(users) == 2
        assert "user1" in users
        assert "user2" in users

        assert authenticate("user1", "pass1") is True
        assert authenticate("user2", "pass2") is True
        assert authenticate("user1", "pass2") is False
