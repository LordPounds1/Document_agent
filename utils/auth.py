"""
Аутентификация для Streamlit приложения.

Простая система логин/пароль для защиты доступа к приложению.
Пароли хранятся в виде хэшей (bcrypt/hashlib).
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

# Файл с пользователями (создаётся при первом запуске)
USERS_FILE = Path(__file__).parent.parent / ".users"


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Хэширование пароля с солью.

    Args:
        password: Пароль в открытом виде
        salt: Соль (генерируется если не указана)

    Returns:
        (hash, salt) в hex формате
    """
    if salt is None:
        salt = secrets.token_bytes(32)
    else:
        salt = bytes.fromhex(salt) if isinstance(salt, str) else salt

    # PBKDF2 с SHA-256, 100000 итераций
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        100000
    )

    return key.hex(), salt.hex()


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Проверка пароля.

    Args:
        password: Пароль для проверки
        stored_hash: Сохранённый хэш
        salt: Соль

    Returns:
        True если пароль верный
    """
    computed_hash, _ = _hash_password(password.encode('utf-8'), salt)
    return hmac.compare_digest(computed_hash, stored_hash)


def _load_users() -> dict:
    """Загрузка пользователей из файла."""
    users = {}

    if USERS_FILE.exists():
        try:
            for line in USERS_FILE.read_text(encoding='utf-8').strip().split('\n'):
                if line and ':' in line:
                    parts = line.strip().split(':')
                    if len(parts) == 3:
                        username, hash_hex, salt_hex = parts
                        users[username] = {'hash': hash_hex, 'salt': salt_hex}
        except Exception as e:
            logger.error(f"Ошибка загрузки пользователей: {e}")

    return users


def _save_user(username: str, password: str):
    """Сохранение пользователя."""
    password_hash, salt = _hash_password(password)

    # Добавляем к файлу
    with open(USERS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{username}:{password_hash}:{salt}\n")

    # Защищаем файл (только для владельца)
    import contextlib
    with contextlib.suppress(Exception):
        os.chmod(USERS_FILE, 0o600)  # Windows может не поддерживать chmod


def create_admin_user(username: str = "admin", password: str | None = None) -> str:
    """Создание администратора при первом запуске.

    Args:
        username: Имя пользователя
        password: Пароль (генерируется если не указан)

    Returns:
        Пароль (для отображения пользователю)
    """
    if password is None:
        # Генерируем безопасный пароль
        password = secrets.token_urlsafe(12)

    _save_user(username, password)
    logger.info(f"Создан пользователь: {username}")

    return password


def check_first_run() -> bool:
    """Проверка первого запуска (нет пользователей)."""
    return not USERS_FILE.exists() or USERS_FILE.stat().st_size == 0


def authenticate(username: str, password: str) -> bool:
    """Аутентификация пользователя.

    Args:
        username: Имя пользователя
        password: Пароль

    Returns:
        True если аутентификация успешна
    """
    users = _load_users()

    if username not in users:
        # Защита от timing attack - всё равно проверяем хэш
        _hash_password(password)
        return False

    user = users[username]
    return _verify_password(password, user['hash'], user['salt'])


def require_auth() -> bool:
    """Проверка аутентификации в Streamlit.

    Показывает форму логина если пользователь не авторизован.

    Returns:
        True если пользователь авторизован
    """
    # Инициализация состояния
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'auth_username' not in st.session_state:
        st.session_state.auth_username = None
    if 'login_attempts' not in st.session_state:
        st.session_state.login_attempts = 0
    if 'lockout_until' not in st.session_state:
        st.session_state.lockout_until = 0

    # Уже авторизован
    if st.session_state.authenticated:
        return True

    # Проверка первого запуска
    if check_first_run():
        _show_setup_form()
        return False

    # Показываем форму логина
    _show_login_form()
    return False


def _show_setup_form():
    """Форма первоначальной настройки."""
    st.markdown("## 🔐 Первоначальная настройка")
    st.info("Создайте учётную запись администратора для защиты приложения.")

    with st.form("setup_form"):
        username = st.text_input("Имя пользователя", value="admin")
        password = st.text_input("Пароль", type="password",
                                  help="Минимум 8 символов")
        password_confirm = st.text_input("Подтвердите пароль", type="password")

        submitted = st.form_submit_button("Создать учётную запись", type="primary")

        if submitted:
            # Валидация
            if len(username) < 3:
                st.error("Имя пользователя должно быть минимум 3 символа")
            elif len(password) < 8:
                st.error("Пароль должен быть минимум 8 символов")
            elif password != password_confirm:
                st.error("Пароли не совпадают")
            else:
                create_admin_user(username, password)
                st.success("✅ Учётная запись создана! Обновите страницу для входа.")
                time.sleep(1)
                st.rerun()


def _show_login_form():
    """Форма входа."""
    # Центрируем форму
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("## 🔐 Вход в систему")
        st.markdown("**Document Processing Agent**")

        # Проверка блокировки
        if st.session_state.lockout_until > time.time():
            remaining = int(st.session_state.lockout_until - time.time())
            st.error(f"⏳ Слишком много попыток. Подождите {remaining} секунд.")
            return

        with st.form("login_form"):
            username = st.text_input("Имя пользователя")
            password = st.text_input("Пароль", type="password")

            submitted = st.form_submit_button("Войти", type="primary",
                                               use_container_width=True)

            if submitted:
                if authenticate(username, password):
                    st.session_state.authenticated = True
                    st.session_state.auth_username = username
                    st.session_state.login_attempts = 0
                    logger.info(f"Успешный вход: {username}")
                    st.rerun()
                else:
                    st.session_state.login_attempts += 1
                    logger.warning(f"Неудачная попытка входа: {username}")

                    # Блокировка после 5 попыток
                    if st.session_state.login_attempts >= 5:
                        st.session_state.lockout_until = time.time() + 300  # 5 минут
                        st.error("⛔ Слишком много неудачных попыток. Блокировка на 5 минут.")
                    else:
                        remaining = 5 - st.session_state.login_attempts
                        st.error(f"❌ Неверные учётные данные. Осталось попыток: {remaining}")


def logout():
    """Выход из системы."""
    st.session_state.authenticated = False
    st.session_state.auth_username = None
    logger.info("Пользователь вышел из системы")


def get_current_user() -> str | None:
    """Получение текущего пользователя."""
    return st.session_state.get('auth_username')


def show_user_menu():
    """Показать меню пользователя в sidebar."""
    if st.session_state.get('authenticated'):
        st.sidebar.divider()
        st.sidebar.markdown(f"👤 **{get_current_user()}**")
        if st.sidebar.button("🚪 Выйти", use_container_width=True):
            logout()
            st.rerun()
