"""Упрощённый агент для работы с почтой."""

from datetime import datetime
from email.header import decode_header
import contextlib
import email
import imaplib
import io
import logging
import socket
# Security: никогда не логируем пароли
logger = logging.getLogger(__name__)

# Retry и metrics
try:
    from utils.metrics import metrics
    RETRY_AVAILABLE = True
except ImportError:
    RETRY_AVAILABLE = False
    logger.warning("Retry/metrics modules not available")


def _safe_error_message(error: Exception) -> str:
    """Создание безопасного сообщения об ошибке без чувствительных данных."""
    error_str = str(error)
    # Маскируем потенциальные пароли в сообщениях ошибок
    import re
    error_str = re.sub(r'(password|passwd|pwd)[=:\s]+\S+', r'\1=****', error_str, flags=re.IGNORECASE)
    error_str = re.sub(r'LOGIN\s+\S+\s+\S+', 'LOGIN **** ****', error_str, flags=re.IGNORECASE)
    return error_str


class EmailAgent:
    """Агент для работы с почтой (IMAP)"""

    # Настройки для разных почтовых провайдеров
    PROVIDERS = {
        'gmail.com': {'imap': 'imap.gmail.com', 'port': 993},
        'googlemail.com': {'imap': 'imap.gmail.com', 'port': 993},
        'yandex.ru': {'imap': 'imap.yandex.ru', 'port': 993},
        'yandex.com': {'imap': 'imap.yandex.com', 'port': 993},
        'ya.ru': {'imap': 'imap.yandex.ru', 'port': 993},
        'mail.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'inbox.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'list.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'bk.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'outlook.com': {'imap': 'outlook.office365.com', 'port': 993},
        'hotmail.com': {'imap': 'outlook.office365.com', 'port': 993},
    }

    def __init__(self):
        self.imap = None
        self.connected = False
        self.email_address = None
        self.provider_settings = None

    def _detect_provider(self, email_address: str) -> dict:
        """Определение настроек по email адресу"""
        domain = email_address.split('@')[-1].lower()

        if domain in self.PROVIDERS:
            return self.PROVIDERS[domain]

        # Default - пробуем imap.domain
        return {'imap': f'imap.{domain}', 'port': 993}

    def connect(self, email_address: str, password: str) -> bool:
        """Подключение к почтовому серверу с retry-логикой.

        Args:
            email_address: Email адрес
            password: Пароль (для Gmail - App Password)

        Returns:
            True если подключение успешно
        """
        self.email_address = email_address
        self.provider_settings = self._detect_provider(email_address)

        server = self.provider_settings['imap']
        port = self.provider_settings['port']

        # Попытка подключения с retry
        return self._connect_with_retry(server, port, email_address, password)

    def _connect_with_retry(
        self, server: str, port: int, email_address: str, password: str
    ) -> bool:
        """Внутренний метод подключения с повторными попытками."""
        max_attempts = 3
        base_delay = 2.0

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Подключение к {server}:{port} (попытка {attempt}/{max_attempts})...")

                # Устанавливаем таймаут для socket
                socket.setdefaulttimeout(30)

                self.imap = imaplib.IMAP4_SSL(server, port)
                self.imap.login(email_address, password)
                self.connected = True

                logger.info(f"✅ Успешное подключение к {server}")

                # Записываем метрику
                if RETRY_AVAILABLE:
                    metrics.increment("email_connections_total", labels={"status": "success"})

                return True

            except imaplib.IMAP4.error:
                # Ошибка аутентификации - не повторяем
                logger.error(f"❌ Ошибка IMAP аутентификации для {email_address.split('@')[-1]}")
                self.connected = False
                if RETRY_AVAILABLE:
                    metrics.increment("email_connections_total", labels={"status": "auth_error"})
                return False

            except (TimeoutError, ConnectionError, OSError) as e:
                # Сетевые ошибки - повторяем
                safe_error = _safe_error_message(e)
                logger.warning(f"⚠️ Сетевая ошибка (попытка {attempt}): {safe_error}")

                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logger.info(f"⏳ Повтор через {delay:.1f} сек...")
                    import time
                    time.sleep(delay)
                else:
                    logger.error(f"❌ Не удалось подключиться после {max_attempts} попыток")
                    self.connected = False
                    if RETRY_AVAILABLE:
                        metrics.increment("email_connections_total", labels={"status": "network_error"})
                    return False

            except Exception as e:
                # Прочие ошибки
                safe_error = _safe_error_message(e)
                logger.error(f"❌ Ошибка подключения: {safe_error}")
                self.connected = False
                if RETRY_AVAILABLE:
                    metrics.increment("email_connections_total", labels={"status": "error"})
                return False

        return False

    def disconnect(self):
        """Отключение от сервера"""
        if self.connected and self.imap:
            with contextlib.suppress(Exception):
                self.imap.logout()
            self.connected = False
            logger.info("Отключено от почтового сервера")

    def fetch_emails(self, folder: str = "INBOX",
                     unread_only: bool = True,
                     limit: int = 50) -> list[dict]:
        """Получение писем из папки

        Args:
            folder: Папка (INBOX, Sent, и т.д.)
            unread_only: Только непрочитанные
            limit: Максимум писем

        Returns:
            Список писем
        """
        if not self.connected:
            logger.warning("Нет подключения к почте")
            return []

        emails = []
        try:
            # Выбираем папку
            status, _ = self.imap.select(folder)
            if status != 'OK':
                logger.error(f"Не удалось открыть папку {folder}")
                return []

            # Поиск писем
            search_criteria = 'UNSEEN' if unread_only else 'ALL'
            status, messages = self.imap.search(None, search_criteria)

            if status != 'OK':
                return []

            message_nums = messages[0].split()
            # Берём последние limit писем
            message_nums = message_nums[-limit:]

            logger.info(f"Найдено {len(message_nums)} писем")

            for num in message_nums:
                try:
                    email_data = self._fetch_email(num)
                    if email_data:
                        emails.append(email_data)
                except Exception as e:
                    logger.warning(f"Ошибка обработки письма {num}: {e}")

        except Exception as e:
            logger.error(f"Ошибка получения писем: {e}")

        return emails

    def _fetch_email(self, num: bytes) -> dict | None:
        """Получение одного письма"""
        status, data = self.imap.fetch(num, '(RFC822)')

        if status != 'OK':
            return None

        email_body = data[0][1]
        email_message = email.message_from_bytes(email_body)

        # Декодируем заголовки
        subject = self._decode_header(email_message['Subject'])
        from_addr = self._decode_header(email_message['From'])
        date_str = email_message['Date']
        message_id = email_message['Message-ID']

        # Парсим дату
        try:
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            date = datetime.now()

        # Извлекаем текст
        body = self._extract_body(email_message)

        # Извлекаем вложения
        attachments = self._extract_attachments(email_message)

        return {
            'id': num.decode(),
            'message_id': message_id,
            'subject': subject,
            'from': from_addr,
            'date': date,
            'date_str': date_str,
            'body': body,
            'attachments': attachments,
            'has_attachments': len(attachments) > 0
        }

    def _decode_header(self, header: str) -> str:
        """Декодирование заголовка"""
        if header is None:
            return ""

        decoded_parts = decode_header(header)
        result = []

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(encoding or 'utf-8', errors='replace'))
                except (LookupError, UnicodeDecodeError):
                    result.append(part.decode('utf-8', errors='replace'))
            else:
                result.append(part)

        return ''.join(result)

    def _extract_body(self, msg) -> str:
        """Извлечение текста письма"""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='replace')
                        break
                    except (UnicodeDecodeError, AttributeError, LookupError):
                        pass
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='replace')
            except (UnicodeDecodeError, AttributeError, LookupError):
                body = str(msg.get_payload())

        return body

    def _extract_attachments(self, msg) -> list[dict]:
        """Извлечение вложений с санитизацией имён файлов"""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header(filename)
                        # Санитизация имени файла для предотвращения path traversal
                        filename = self._sanitize_filename(filename)
                        content = part.get_payload(decode=True)

                        # Ограничение размера вложения (50 MB)
                        max_size = 50 * 1024 * 1024
                        if content and len(content) > max_size:
                            logger.warning(f"Вложение {filename} слишком большое, пропущено")
                            continue

                        attachments.append({
                            'filename': filename,
                            'content': content,
                            'size': len(content) if content else 0,
                            'content_type': part.get_content_type()
                        })

        return attachments

    def _sanitize_filename(self, filename: str) -> str:
        """Санитизация имени файла для предотвращения path traversal"""
        if not filename:
            return "unnamed"

        # Убираем путь, оставляем только имя файла
        filename = filename.replace('\\', '/').split('/')[-1]

        # Удаляем опасные символы
        dangerous = ['..', '~', '\x00', ':', '*', '?', '"', '<', '>', '|']
        for char in dangerous:
            filename = filename.replace(char, '_')

        # Ограничиваем длину
        if len(filename) > 200:
            name_parts = filename.rsplit('.', 1)
            if len(name_parts) == 2:
                name, ext = name_parts
                filename = name[:190] + '.' + ext
            else:
                filename = filename[:200]

        return filename or "unnamed"

    def mark_as_read(self, email_id: str):
        """Пометить письмо как прочитанное"""
        if self.connected:
            with contextlib.suppress(Exception):
                self.imap.store(email_id.encode(), '+FLAGS', '\\Seen')

    def get_attachment_text(self, attachment: dict) -> str:  # type: ignore[return]
        """Извлечение текста из вложения"""
        filename = attachment.get('filename', '').lower()
        content = attachment.get('content', b'')

        if not content:
            return ""

        try:
            # DOCX файлы
            if filename.endswith('.docx'):
                import docx2txt
                return docx2txt.process(io.BytesIO(content))

            # PDF файлы
            elif filename.endswith('.pdf'):
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(content))
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    return text
                except ImportError:
                    logger.warning("PyPDF2 not installed for PDF processing")
                    return ""

            # TXT файлы
            elif filename.endswith('.txt'):
                return content.decode('utf-8', errors='replace')

        except Exception as e:
            logger.error(f"Ошибка извлечения текста из {filename}: {e}")

        return ""

