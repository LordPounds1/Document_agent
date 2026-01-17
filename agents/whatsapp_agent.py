"""Агент для работы с WhatsApp.

Поддерживает два режима:
1. Автоматический мониторинг через WhatsApp Web (требует whatsapp-web.py или selenium)
2. Импорт экспортированных чатов из WhatsApp (ручной режим)

Для автоматического режима используется неофициальный API через WhatsApp Web.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Опциональные зависимости
SELENIUM_AVAILABLE = False
WHATSAPP_LIB_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    SELENIUM_AVAILABLE = True
except ImportError:
    logger.info("Selenium не установлен. Автоматический режим WhatsApp недоступен.")


@dataclass
class WhatsAppMessage:
    """Сообщение из WhatsApp."""

    sender: str
    content: str
    timestamp: datetime
    chat_name: str
    has_attachment: bool = False
    attachment_path: str | None = None
    attachment_type: str | None = None  # document, image, video, audio
    is_contract: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WhatsAppChat:
    """Чат WhatsApp с сообщениями."""

    name: str
    messages: list[WhatsAppMessage] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    exported_at: datetime | None = None
    source: str = "export"  # export, web, api


class WhatsAppAgent:
    """Агент для работы с WhatsApp.

    Режимы работы:
    1. EXPORT - импорт экспортированных чатов (.txt файлы из WhatsApp)
    2. WEB - автоматический мониторинг через WhatsApp Web (Selenium)
    3. API - через WhatsApp Business API (требует настройки)
    """

    # Паттерны для парсинга экспортированных чатов WhatsApp
    # Формат: [DD.MM.YYYY, HH:MM:SS] Sender: Message
    # или: DD.MM.YYYY, HH:MM - Sender: Message
    MESSAGE_PATTERNS = [
        # Формат с квадратными скобками: [14.01.2026, 15:30:45] Иван: Текст
        r'\[(\d{1,2}\.\d{1,2}\.\d{4}),\s*(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:]+):\s*(.+)',
        # Формат без скобок: 14.01.2026, 15:30 - Иван: Текст
        r'(\d{1,2}\.\d{1,2}\.\d{4}),\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*([^:]+):\s*(.+)',
        # Американский формат: 1/14/26, 3:30 PM - John: Text
        r'(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}\s*(?:AM|PM)?)\s*-\s*([^:]+):\s*(.+)',
    ]

    # Системные сообщения WhatsApp (игнорируем)
    SYSTEM_MESSAGE_PATTERNS = [
        r'Сообщения и звонки защищены',
        r'Messages and calls are end-to-end encrypted',
        r'изменил\(а\) значок группы',
        r'изменил\(а\) описание',
        r'добавил\(а\)',
        r'удалил\(а\)',
        r'вышел\(ла\) из группы',
        r'создал\(а\) группу',
        r'changed the group',
        r'added you',
        r'removed',
        r'left',
        r'created group',
    ]

    # Паттерны для обнаружения вложений
    ATTACHMENT_PATTERNS = [
        (r'<Мультимедиа не включены>', 'media'),
        (r'<Media omitted>', 'media'),
        (r'документ прикреплён', 'document'),
        (r'document attached', 'document'),
        (r'изображение', 'image'),
        (r'image', 'image'),
        (r'видео', 'video'),
        (r'video', 'video'),
        (r'\.pdf', 'document'),
        (r'\.docx?', 'document'),
        (r'\.xlsx?', 'document'),
    ]

    # Ключевые слова для определения договоров
    CONTRACT_KEYWORDS = [
        'договор', 'контракт', 'соглашение', 'акт',
        'счёт', 'счет', 'invoice', 'contract', 'agreement',
        'подпиши', 'на подпись', 'согласуй', 'утверди',
        'приложение к договору', 'дополнительное соглашение',
        'коммерческое предложение', 'кп', 'спецификация'
    ]

    def __init__(
        self,
        downloads_dir: str = "whatsapp_downloads",
        session_dir: str = ".whatsapp_session",
        auto_mode: bool = False
    ):
        """Инициализация агента.

        Args:
            downloads_dir: Директория для скачивания вложений
            session_dir: Директория для хранения сессии WhatsApp Web
            auto_mode: Использовать автоматический режим (Selenium)
        """
        self.downloads_dir = Path(downloads_dir)
        self.session_dir = Path(session_dir)
        self.auto_mode = auto_mode and SELENIUM_AVAILABLE

        self.driver = None
        self.connected = False
        self.chats: dict[str, WhatsAppChat] = {}

        # Callbacks для обработки сообщений
        self.on_message_callback: Callable | None = None
        self.on_document_callback: Callable | None = None

        # Создаём директории
        self.downloads_dir.mkdir(exist_ok=True)
        self.session_dir.mkdir(exist_ok=True)

    # ==================== ЭКСПОРТ ЧАТОВ (Ручной режим) ====================

    def parse_exported_chat(self, file_path: str, encoding: str = 'utf-8') -> WhatsAppChat:
        """Парсинг экспортированного чата из WhatsApp.

        WhatsApp позволяет экспортировать чаты:
        Чат → Ещё → Экспорт чата → Без медиафайлов / С медиафайлами

        Args:
            file_path: Путь к .txt файлу экспорта
            encoding: Кодировка файла

        Returns:
            WhatsAppChat с распарсенными сообщениями
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path_obj}")

        # Определяем имя чата из имени файла
        chat_name = file_path_obj.stem.replace("WhatsApp Chat with ", "").replace("Чат WhatsApp с ", "")

        chat = WhatsAppChat(
            name=chat_name,
            exported_at=datetime.now(),
            source="export"
        )

        # Читаем файл
        try:
            with open(file_path, encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError:
            # Пробуем другие кодировки
            for enc in ['utf-8-sig', 'cp1251', 'latin-1']:
                try:
                    with open(file_path, encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"Не удалось определить кодировку файла: {file_path}")

        # Парсим сообщения
        lines = content.split('\n')
        current_message = None
        participants = set()

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Проверяем системные сообщения
            if self._is_system_message(line):
                continue

            # Пробуем распарсить как новое сообщение
            parsed = self._parse_message_line(line, chat_name)

            if parsed:
                # Сохраняем предыдущее сообщение
                if current_message:
                    chat.messages.append(current_message)

                current_message = parsed
                participants.add(parsed.sender)
            elif current_message:
                # Многострочное сообщение - добавляем к текущему
                current_message.content += '\n' + line

        # Добавляем последнее сообщение
        if current_message:
            chat.messages.append(current_message)

        chat.participants = list(participants)

        # Помечаем сообщения с договорами
        self._mark_contract_messages(chat)

        logger.info(f"Распарсено {len(chat.messages)} сообщений из чата '{chat_name}'")
        return chat

    def _parse_message_line(self, line: str, chat_name: str) -> WhatsAppMessage | None:
        """Парсинг одной строки сообщения."""
        for pattern in self.MESSAGE_PATTERNS:
            match = re.match(pattern, line)
            if match:
                date_str, time_str, sender, content = match.groups()

                # Парсим дату и время
                timestamp = self._parse_datetime(date_str, time_str)

                # Проверяем на вложения
                has_attachment, attachment_type = self._check_attachment(content)

                return WhatsAppMessage(
                    sender=sender.strip(),
                    content=content.strip(),
                    timestamp=timestamp,
                    chat_name=chat_name,
                    has_attachment=has_attachment,
                    attachment_type=attachment_type
                )

        return None

    def _parse_datetime(self, date_str: str, time_str: str) -> datetime:
        """Парсинг даты и времени из разных форматов."""
        # Убираем AM/PM если есть
        time_str = time_str.strip()
        is_pm = 'PM' in time_str.upper()
        is_am = 'AM' in time_str.upper()
        time_str = re.sub(r'\s*(AM|PM)', '', time_str, flags=re.IGNORECASE)

        # Пробуем разные форматы даты
        date_formats = [
            '%d.%m.%Y',  # 14.01.2026
            '%d.%m.%y',  # 14.01.26
            '%m/%d/%Y',  # 1/14/2026
            '%m/%d/%y',  # 1/14/26
        ]

        date_obj = None
        for fmt in date_formats:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue

        if not date_obj:
            date_obj = datetime.now()

        # Парсим время
        time_formats = ['%H:%M:%S', '%H:%M']
        time_obj = None
        for fmt in time_formats:
            try:
                time_obj = datetime.strptime(time_str, fmt)
                break
            except ValueError:
                continue

        if time_obj:
            hour = time_obj.hour
            if is_pm and hour < 12:
                hour += 12
            elif is_am and hour == 12:
                hour = 0

            return date_obj.replace(
                hour=hour,
                minute=time_obj.minute,
                second=time_obj.second if hasattr(time_obj, 'second') else 0
            )

        return date_obj

    def _is_system_message(self, line: str) -> bool:
        """Проверка, является ли сообщение системным."""
        for pattern in self.SYSTEM_MESSAGE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def _check_attachment(self, content: str) -> tuple[bool, str | None]:
        """Проверка на наличие вложения."""
        for pattern, att_type in self.ATTACHMENT_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return True, att_type
        return False, None

    def _mark_contract_messages(self, chat: WhatsAppChat):
        """Помечает сообщения, которые могут содержать договоры."""
        for message in chat.messages:
            content_lower = message.content.lower()

            # Проверяем ключевые слова
            for keyword in self.CONTRACT_KEYWORDS:
                if keyword in content_lower:
                    message.is_contract = True
                    break

            # Документы с высокой вероятностью - договоры
            if message.attachment_type == 'document':
                message.is_contract = True

    def import_chat_folder(self, folder_path: str) -> list[WhatsAppChat]:
        """Импорт всех экспортированных чатов из папки.

        Args:
            folder_path: Путь к папке с экспортированными чатами

        Returns:
            Список распарсенных чатов
        """
        folder = Path(folder_path)
        chats = []

        for file_path in folder.glob("*.txt"):
            try:
                chat = self.parse_exported_chat(str(file_path))
                chats.append(chat)
                self.chats[chat.name] = chat
            except Exception as e:
                logger.error(f"Ошибка парсинга {file_path}: {e}")

        return chats

    def get_contract_messages(self, chat: WhatsAppChat | None = None) -> list[WhatsAppMessage]:
        """Получение сообщений с потенциальными договорами.

        Args:
            chat: Конкретный чат или None для всех чатов

        Returns:
            Список сообщений с договорами
        """
        messages = []

        if chat:
            messages = [m for m in chat.messages if m.is_contract]
        else:
            for c in self.chats.values():
                messages.extend([m for m in c.messages if m.is_contract])

        return messages

    # ==================== WHATSAPP WEB (Автоматический режим) ====================

    def connect_web(self, headless: bool = False) -> bool:
        """Подключение к WhatsApp Web через Selenium.

        При первом запуске нужно отсканировать QR-код.
        Сессия сохраняется для последующих запусков.

        Args:
            headless: Запуск без отображения браузера

        Returns:
            True если подключение успешно
        """
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium не установлен. Установите: pip install selenium")
            return False

        try:
            # Настройка Chrome
            options = Options()
            options.add_argument(f"--user-data-dir={self.session_dir.absolute()}")

            if headless:
                options.add_argument("--headless")

            # Отключаем уведомления
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-popup-blocking")

            # Инициализация драйвера
            driver = webdriver.Chrome(options=options)
            self.driver = driver  # type: ignore[assignment]
            driver.get("https://web.whatsapp.com")

            logger.info("Ожидание загрузки WhatsApp Web...")
            logger.info("Если QR-код не был отсканирован ранее, отсканируйте его в браузере")

            # Ждём загрузки чатов (до 60 секунд)
            if driver:
                wait = WebDriverWait(driver, 60)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-list"]')))

            self.connected = True
            logger.info("✅ Подключено к WhatsApp Web")
            return True

        except Exception as e:
            logger.error(f"Ошибка подключения к WhatsApp Web: {e}")
            return False

    def get_chats_list(self) -> list[str]:
        """Получение списка чатов из WhatsApp Web."""
        if not self.connected or not self.driver:
            return []

        try:
            chat_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="cell-frame-title"]')
            return [el.text for el in chat_elements if el.text]
        except Exception as e:
            logger.error(f"Ошибка получения списка чатов: {e}")
            return []

    def open_chat(self, chat_name: str) -> bool:
        """Открытие чата по имени."""
        if not self.connected or not self.driver:
            return False

        try:
            # Ищем чат в списке
            search_box = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list-search"]')
            search_box.clear()
            search_box.send_keys(chat_name)

            # Ждём результатов
            import time
            time.sleep(1)

            # Кликаем на первый результат
            chat = self.driver.find_element(By.CSS_SELECTOR, f'[title="{chat_name}"]')
            chat.click()

            return True
        except Exception as e:
            logger.error(f"Ошибка открытия чата '{chat_name}': {e}")
            return False

    def download_documents(self, chat_name: str) -> list[str]:
        """Скачивание документов из чата.

        Args:
            chat_name: Имя чата

        Returns:
            Список путей к скачанным файлам
        """
        if not self.connected or not self.driver:
            return []

        downloaded = []

        try:
            # Открываем чат
            if not self.open_chat(chat_name):
                return []

            # Находим все документы
            doc_elements = self.driver.find_elements(
                By.CSS_SELECTOR,
                '[data-testid="document-thumb"]'
            )

            for doc in doc_elements:
                try:
                    # Кликаем для скачивания
                    doc.click()
                    import time
                    time.sleep(2)

                    # Находим кнопку скачивания
                    download_btn = self.driver.find_element(
                        By.CSS_SELECTOR,
                        '[data-testid="download"]'
                    )
                    download_btn.click()
                    time.sleep(1)

                    # Получаем имя файла (примерно)
                    # В реальности нужно отслеживать папку загрузок
                    downloaded.append(f"document_{len(downloaded)}")

                except Exception as e:
                    logger.warning(f"Ошибка скачивания документа: {e}")

            logger.info(f"Скачано {len(downloaded)} документов из чата '{chat_name}'")

        except Exception as e:
            logger.error(f"Ошибка скачивания документов: {e}")

        return downloaded

    def disconnect(self):
        """Отключение от WhatsApp Web."""
        if self.driver:
            self.driver.quit()
            self.driver = None
        self.connected = False

    # ==================== ОБРАБОТКА ДОГОВОРОВ ====================

    def process_messages_for_contracts(
        self,
        chat: WhatsAppChat,
        processor_callback: Callable[[str], dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Обработка сообщений чата для извлечения договоров.

        Args:
            chat: Чат для обработки
            processor_callback: Функция обработки текста договора

        Returns:
            Список результатов обработки
        """
        results = []

        contract_messages = [m for m in chat.messages if m.is_contract]

        for message in contract_messages:
            try:
                # Формируем контекст сообщения
                context = {
                    'source': 'whatsapp',
                    'chat_name': chat.name,
                    'sender': message.sender,
                    'timestamp': message.timestamp.isoformat(),
                    'has_attachment': message.has_attachment,
                    'attachment_type': message.attachment_type,
                }

                # Если есть вложение-документ, нужно его обработать отдельно
                if message.attachment_type == 'document' and message.attachment_path:
                    # Читаем документ
                    doc_content = self._read_document(message.attachment_path)
                    if doc_content:
                        result = processor_callback(doc_content)
                        result['context'] = context
                        results.append(result)
                else:
                    # Обрабатываем текст сообщения
                    result = processor_callback(message.content)
                    result['context'] = context
                    results.append(result)

            except Exception as e:
                logger.error(f"Ошибка обработки сообщения: {e}")

        return results

    def _read_document(self, file_path: str) -> str | None:  # type: ignore[return]
        """Чтение документа (DOCX, PDF, TXT)."""
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            return None

        suffix = file_path_obj.suffix.lower()

        try:
            if suffix == '.txt':
                with open(file_path_obj, encoding='utf-8') as f:
                    return f.read()  # type: ignore[return]

            elif suffix == '.docx':
                try:
                    import docx2txt
                    return docx2txt.process(str(file_path_obj))  # type: ignore[return, no-any-return]
                except ImportError:
                    logger.error("docx2txt не установлен")
                    return None

            elif suffix == '.pdf':
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text() + "\n"
                        return text
                except ImportError:
                    logger.error("PyPDF2 не установлен")
                    return None

        except Exception as e:
            logger.error(f"Ошибка чтения документа {file_path}: {e}")

        return None

    def get_stats(self) -> dict[str, Any]:
        """Статистика агента."""
        total_messages = sum(len(c.messages) for c in self.chats.values())
        contract_messages = sum(
            len([m for m in c.messages if m.is_contract])
            for c in self.chats.values()
        )

        return {
            'total_chats': len(self.chats),
            'total_messages': total_messages,
            'contract_messages': contract_messages,
            'auto_mode_available': SELENIUM_AVAILABLE,
            'connected': self.connected,
        }


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def create_whatsapp_agent(
    auto_mode: bool = False,
    downloads_dir: str = "whatsapp_downloads"
) -> WhatsAppAgent:
    """Фабричная функция для создания агента.

    Args:
        auto_mode: Использовать автоматический режим
        downloads_dir: Директория для загрузок

    Returns:
        Настроенный WhatsAppAgent
    """
    return WhatsAppAgent(
        downloads_dir=downloads_dir,
        auto_mode=auto_mode
    )
