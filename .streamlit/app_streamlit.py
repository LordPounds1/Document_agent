"""
📧 Document Processing Agent - Web Interface.

Веб-интерфейс для обработки договоров из почты

Функциональность:
1. Ввод email (Gmail, Yandex и др.)
2. Обработка почты, поиск писем с договорами
3. Анализ договоров с помощью LLM
4. Создание Excel таблицы с результатами
5. Мониторинг новых писем
"""

import importlib.util
import io
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st  # noqa: I001
# Добавляем родительскую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent))

# Security imports
from utils.auth import require_auth, show_user_menu
from utils.security import (
    login_rate_limiter,
    sanitize_html,
    validate_email,
    validate_password,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Кастомный handler для отображения логов в Streamlit
class StreamlitLogHandler(logging.Handler):
    """Handler для сохранения логов в session_state (потокобезопасный)."""

    def __init__(self, max_lines: int = 200):
        super().__init__()
        self.max_lines = max_lines
        self.setLevel(logging.INFO)
        self._logs = []  # Внутренний список логов
        self._lock = threading.Lock()

        # Форматтер для логов (упрощённый формат)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        self.setFormatter(formatter)

    def emit(self, record):
        """Сохраняет лог во внутренний список (потокобезопасно)."""
        try:
            # Форматируем сообщение
            log_entry = self.format(record)

            with self._lock:
                # Добавляем в начало списка (новые сверху)
                self._logs.insert(0, log_entry)

                # Ограничиваем количество логов
                if len(self._logs) > self.max_lines:
                    self._logs = self._logs[:self.max_lines]
        except Exception as e:
            # Игнорируем ошибки в handler, чтобы не ломать приложение
            logger.debug(f"Error in log handler: {e}")

    def get_logs(self) -> list:
        """Получить копию логов (потокобезопасно)."""
        with self._lock:
            return self._logs.copy()

    def clear_logs(self):
        """Очистить логи (потокобезопасно)."""
        with self._lock:
            self._logs = []

# Инициализируем handler для WhatsApp логов
whatsapp_log_handler = StreamlitLogHandler(max_lines=200)

# Добавляем handler к логгерам WhatsApp (Playwright)
for logger_name in ['whatsapp', 'whatsapp.client', 'whatsapp.adapter', 'whatsapp.chat_iterator', 'whatsapp.message_scanner', 'whatsapp.downloader']:
    wa_logger = logging.getLogger(logger_name)
    wa_logger.addHandler(whatsapp_log_handler)
    wa_logger.setLevel(logging.INFO)

# Также добавляем к корневому логгеру для перехвата всех логов WhatsApp
root_logger = logging.getLogger()
root_logger.addHandler(whatsapp_log_handler)

# Импорт компонентов (после sys.path.insert)
from agents.email_agent import EmailAgent  # noqa: E402, I001
from agents.whatsapp_agent import WhatsAppAgent  # noqa: E402, I001
from core.rag import SimpleRAG  # noqa: E402, I001
from processors.document import DocumentProcessor  # noqa: E402, I001
# Импорт WhatsApp Playwright модуля
if importlib.util.find_spec('playwright') is not None:
    from whatsapp.monitor import (  # noqa: E402, I001
        WhatsAppMonitor,
        create_monitor,
        get_monitor,
        stop_monitor,
    )
    PLAYWRIGHT_AVAILABLE = True
else:
    PLAYWRIGHT_AVAILABLE = False
    WhatsAppMonitor = None

# Конфигурация страницы
st.set_page_config(
    page_title="📄 Document Processing Agent",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Стили
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .status-connected {
        color: #28a745;
        font-weight: bold;
    }
    .status-disconnected {
        color: #dc3545;
        font-weight: bold;
    }
    .contract-found {
        background-color: #d4edda;
        color: #155724 !important;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border: 1px solid #c3e6cb;
    }
    .contract-found strong {
        color: #155724 !important;
    }
    .contract-found br {
        color: #155724 !important;
    }
    .info-box {
        background-color: #e7f3ff;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Инициализация состояния сессии"""
    if 'email_agent' not in st.session_state:
        st.session_state.email_agent = EmailAgent()
    if 'whatsapp_agent' not in st.session_state:
        st.session_state.whatsapp_agent = WhatsAppAgent()
    # WhatsApp Playwright
    if 'whatsapp_processing' not in st.session_state:
        st.session_state.whatsapp_processing = False
    if 'whatsapp_monitoring' not in st.session_state:
        st.session_state.whatsapp_monitoring = False
    if 'whatsapp_monitor_events' not in st.session_state:
        st.session_state.whatsapp_monitor_events = []
    if 'whatsapp_documents' not in st.session_state:
        st.session_state.whatsapp_documents = []
    if 'whatsapp_stats' not in st.session_state:
        st.session_state.whatsapp_stats = {'chats': 0, 'documents': 0, 'contracts': 0}
    if 'processed_whatsapp_files' not in st.session_state:
        st.session_state.processed_whatsapp_files = set()
    if 'document_processor' not in st.session_state:
        st.session_state.document_processor = None
    if 'rag' not in st.session_state:
        st.session_state.rag = None
    if 'connected' not in st.session_state:
        st.session_state.connected = False
    if 'processed_documents' not in st.session_state:
        st.session_state.processed_documents = []
    if 'processed_email_ids' not in st.session_state:
        st.session_state.processed_email_ids = set()
    if 'order_number' not in st.session_state:
        st.session_state.order_number = 1
    if 'monitoring' not in st.session_state:
        st.session_state.monitoring = False
    if 'last_check' not in st.session_state:
        st.session_state.last_check = None
    if 'scan_all' not in st.session_state:
        st.session_state.scan_all = True


def get_model_path():
    """Получение пути к модели"""
    models_dir = Path("models")
    if models_dir.exists():
        model_files = list(models_dir.glob("*.gguf"))
        if model_files:
            return str(model_files[0])
    return None


def init_document_processor():
    """Инициализация процессора документов"""
    if st.session_state.document_processor is None:
        model_path = get_model_path()
        if model_path:
            st.session_state.document_processor = DocumentProcessor(
                model_path=model_path,
                templates_dir="templates"
            )
            logger.info(f"DocumentProcessor initialized with model: {model_path}")
        else:
            logger.warning("No model found, using basic extraction")


def init_rag():
    """Инициализация RAG системы"""
    if st.session_state.rag is None:
        st.session_state.rag = SimpleRAG(templates_dir="templates")
        logger.info(f"RAG initialized: {st.session_state.rag.get_stats()}")


def connect_email(email_address: str, password: str) -> bool:
    """Подключение к почте"""
    success = st.session_state.email_agent.connect(email_address, password)
    st.session_state.connected = success
    return success


def process_emails(scan_all: bool = True, progress_placeholder=None) -> list:
    """Обработка писем и поиск договоров

    Args:
        scan_all: True = проверить все письма, False = только непрочитанные
        progress_placeholder: Streamlit placeholder для отображения прогресса
    """
    if not st.session_state.connected:
        return []

    init_document_processor()
    init_rag()

    # Получаем письма (все или только непрочитанные)
    if progress_placeholder:
        progress_placeholder.info("📥 Получение списка писем...")

    emails = st.session_state.email_agent.fetch_emails(
        unread_only=not scan_all,  # Если scan_all=True, то unread_only=False
        limit=100  # Увеличиваем лимит для полного сканирования
    )

    if progress_placeholder:
        progress_placeholder.info(f"📧 Найдено {len(emails)} писем. Начинаю анализ...")

    found_contracts = []
    skipped = 0

    # Progress bar
    if progress_placeholder and emails:
        progress_bar = progress_placeholder.progress(0, text="Анализ писем...")

    for idx, email_data in enumerate(emails):
        # Обновляем прогресс
        if progress_placeholder and emails:
            progress = (idx + 1) / len(emails)
            subject = email_data.get('subject', 'Без темы')[:40]
            progress_bar.progress(progress, text=f"📧 [{idx+1}/{len(emails)}] {subject}...")

        # Пропускаем уже обработанные письма
        email_id = email_data.get('id', '')
        if email_id in st.session_state.processed_email_ids:
            skipped += 1
            continue

        contract_text = None
        source = None

        # Проверяем тело письма
        body = email_data.get('body', '')
        if body:
            is_contract, confidence = st.session_state.rag.is_contract(body)
            if is_contract:
                contract_text = body
                source = 'email_body'

        # Проверяем вложения
        if not contract_text:
            for attachment in email_data.get('attachments', []):
                filename = attachment.get('filename', '').lower()

                # Только документы
                if filename.endswith(('.docx', '.pdf', '.txt', '.doc')):
                    text = st.session_state.email_agent.get_attachment_text(attachment)

                    if text:
                        is_contract, confidence = st.session_state.rag.is_contract(text)
                        if is_contract:
                            contract_text = text
                            source = f'attachment:{attachment.get("filename")}'
                            break

        # Если нашли договор - обрабатываем
        if contract_text:
            # Получаем дату без timezone
            email_date = email_data.get('date', datetime.now())
            if hasattr(email_date, 'tzinfo') and email_date.tzinfo is not None:
                email_date = email_date.replace(tzinfo=None)

            # Обрабатываем с LLM
            if st.session_state.document_processor:
                result = st.session_state.document_processor.process_email_with_contract(
                    email_data, contract_text
                )
                # Убираем timezone из даты
                if ('email_date' in result and hasattr(result['email_date'], 'tzinfo') and
                        result['email_date'].tzinfo is not None):
                    result['email_date'] = result['email_date'].replace(tzinfo=None)
            else:
                # Без LLM
                result = {
                    'email_id': email_data.get('id', ''),
                    'email_from': email_data.get('from', ''),
                    'email_subject': email_data.get('subject', ''),
                    'email_date': email_date,
                    'document_type': 'Договор',
                    'summary': contract_text[:150] + '...',
                    'parties': '',
                    'amount': '',
                    'responsible': '',
                    'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }

            # Добавляем порядковый номер
            result['order_number'] = st.session_state.order_number
            result['source'] = source
            st.session_state.order_number += 1

            found_contracts.append(result)

            # Добавляем email_id в обработанные
            st.session_state.processed_email_ids.add(email_id)

            # Помечаем письмо как прочитанное
            st.session_state.email_agent.mark_as_read(email_data['id'])

    # Добавляем к общему списку
    st.session_state.processed_documents.extend(found_contracts)
    st.session_state.last_check = datetime.now()

    return found_contracts


def process_whatsapp_text(text: str, msg, source: str) -> dict | None:
    """Обработка текста из WhatsApp (сообщение или вложение)."""
    if not text or len(text) < 20:
        return None

    msg_id = getattr(msg, 'id', '')
    if msg_id and msg_id in st.session_state.processed_whatsapp_message_ids:
        return None

    init_document_processor()
    init_rag()

    is_contract = False
    if st.session_state.rag:
        is_contract, _ = st.session_state.rag.is_contract(text)

    if not is_contract:
        return None

    if st.session_state.document_processor:
        info = st.session_state.document_processor.extract_contract_info(text)
    else:
        info = {'document_type': 'Договор', 'summary': text[:150]}

    msg_date = getattr(msg, 'timestamp', None) or datetime.now()
    if hasattr(msg_date, 'tzinfo') and msg_date.tzinfo is not None:
        msg_date = msg_date.replace(tzinfo=None)

    result = {
        'order_number': st.session_state.order_number,
        'email_id': getattr(msg, 'id', ''),
        'email_from': 'WhatsApp: {}'.format(getattr(msg, 'sender', '')),
        'email_subject': 'Чат: {}'.format(getattr(msg, 'chat_name', '')),
        'email_date': msg_date,
        'document_type': info.get('document_type', 'Договор'),
        'summary': info.get('summary', text[:150]),
        'parties': info.get('parties', ''),
        'amount': info.get('amount', ''),
        'responsible': getattr(msg, 'sender', ''),
        'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'execution_period': info.get('execution_period', ''),
        'penalties': info.get('penalties', ''),
        'source': source
    }

    st.session_state.processed_documents.append(result)
    st.session_state.order_number += 1
    st.session_state.whatsapp_messages.append(msg)
    if msg_id:
        st.session_state.processed_whatsapp_message_ids.add(msg_id)

    return result


def create_excel_dataframe() -> pd.DataFrame:
    """Создание DataFrame для Excel"""
    if not st.session_state.processed_documents:
        return pd.DataFrame()

    df = pd.DataFrame(st.session_state.processed_documents)

    # Переименовываем колонки для Excel
    columns_mapping = {
        'order_number': '№ п/п',
        'email_date': 'Дата входящего',
        'summary': 'Описание документа',
        'email_from': 'Источник',
        'responsible': 'Ответственные',
        'processed_at': 'Дата обработки',
        'document_type': 'Тип документа',
        'email_subject': 'Тема/Чат',
        'parties': 'Стороны договора',
        'amount': 'Сумма',
        'execution_period': 'Срок исполнения',
        'penalties': 'Пени/Штрафы',
        'source': 'Канал'
    }

    df = df.rename(columns=columns_mapping)

    # Порядок колонок
    ordered_columns = [
        '№ п/п', 'Дата входящего', 'Тип документа', 'Описание документа',
        'Стороны договора', 'Сумма', 'Срок исполнения', 'Пени/Штрафы',
        'Источник', 'Ответственные', 'Дата обработки', 'Тема/Чат', 'Канал'
    ]

    # Оставляем только существующие колонки
    existing_columns = [col for col in ordered_columns if col in df.columns]
    df = df[existing_columns]

    return df


def export_to_excel() -> bytes:
    """Экспорт в Excel"""
    df = create_excel_dataframe()

    if df.empty:
        return None

    # Конвертируем datetime с timezone в timezone-unaware
    for col in df.columns:
        if df[col].dtype == 'datetime64[ns, UTC]' or str(df[col].dtype).startswith('datetime'):
            try:
                # Убираем timezone информацию
                df[col] = pd.to_datetime(df[col]).dt.tz_localize(None)
            except (TypeError, ValueError):
                # Если уже без timezone, просто форматируем как строку
                df[col] = df[col].astype(str)

    # Дополнительно проверяем все объекты datetime
    for col in df.columns:
        if df[col].apply(lambda x: hasattr(x, 'tzinfo') and x.tzinfo is not None if hasattr(x, 'tzinfo') else False).any():
            df[col] = df[col].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'replace') and hasattr(x, 'tzinfo') else x)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Документы', index=False)

        # Автоматическая ширина колонок
        worksheet = writer.sheets['Документы']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).map(len).max(),
                len(col)
            )
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

    return output.getvalue()


# ============ MAIN UI ============

def main():
    init_session_state()

    # ===========================================
    # АУТЕНТИФИКАЦИЯ - проверяем ПЕРЕД показом UI
    # ===========================================
    if not require_auth():
        # Пользователь не авторизован - показана форма входа
        return

    # Заголовок
    st.markdown('<h1 class="main-header">📄 Document Processing Agent</h1>', unsafe_allow_html=True)
    st.markdown("**Интеллектуальный агент для обработки договоров из почты**")

    # Боковая панель - настройки
    with st.sidebar:
        # Меню пользователя (показывает имя и кнопку выхода)
        show_user_menu()

        st.header("⚙️ Настройки")

        # Статус подключения
        if st.session_state.connected:
            st.markdown('<p class="status-connected">✅ Подключено к почте</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="status-disconnected">❌ Не подключено</p>', unsafe_allow_html=True)

        st.divider()

        # Форма подключения
        st.subheader("📧 Подключение к почте")

        email_address = st.text_input(
            "Email адрес",
            placeholder="example@gmail.com",
            help="Поддерживаются: Gmail, Yandex, Mail.ru, Outlook"
        )

        password = st.text_input(
            "Пароль приложения",
            type="password",
            help="Для Gmail используйте App Password (не обычный пароль)"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔌 Подключить", use_container_width=True):
                # Валидация входных данных
                if not email_address or not password:
                    st.warning("Введите email и пароль")
                elif not validate_email(email_address):
                    st.error("❌ Некорректный формат email адреса")
                elif not validate_password(password):
                    st.error("❌ Пароль слишком короткий или длинный")
                elif not login_rate_limiter.is_allowed(email_address):
                    remaining = login_rate_limiter.get_remaining_time(email_address)
                    st.error(f"❌ Слишком много попыток. Подождите {remaining} сек.")
                else:
                    with st.spinner("Подключение..."):
                        if connect_email(email_address, password):
                            st.success("✅ Успешно подключено!")
                            login_rate_limiter.reset(email_address)  # Сброс при успехе
                        else:
                            st.error("❌ Ошибка подключения. Проверьте данные.")

        with col2:
            if st.button("🔌 Отключить", use_container_width=True):
                st.session_state.email_agent.disconnect()
                st.session_state.connected = False
                st.info("Отключено")

        st.divider()

        # RAG статистика
        if st.session_state.rag:
            st.subheader("📊 RAG Система")
            stats = st.session_state.rag.get_stats()
            st.metric("Шаблонов договоров", stats['total_templates'])
            st.metric("Синонимов", stats['synonyms_count'])

        st.divider()

        # Кнопка выхода
        st.subheader("🚪 Выход")
        if st.button("❌ Отключиться от почты", use_container_width=True, type="secondary"):
            st.session_state.email_agent.disconnect()
            st.session_state.connected = False
            st.session_state.monitoring = False
            st.info("✅ Сессия завершена. Можете закрыть вкладку браузера.")
            st.rerun()

    # Основной контент
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📬 Обработка почты", "📱 WhatsApp", "🔄 Фоновый мониторинг", "📋 Результаты", "📖 Справка"])

    with tab1:
        st.header("📬 Обработка писем")

        if not st.session_state.connected:
            st.info("👈 Сначала подключитесь к почте в боковой панели")
        else:
            # Настройки сканирования
            st.subheader("⚙️ Режим сканирования")
            col_opt1, col_opt2 = st.columns(2)
            with col_opt1:
                scan_all = st.checkbox(
                    "📧 Сканировать ВСЕ письма",
                    value=True,
                    help="Если включено - проверяются все письма. Если выключено - только непрочитанные."
                )
            with col_opt2:
                st.info(f"✅ Обработано ранее: {len(st.session_state.processed_email_ids)} писем")

            st.divider()

            col1, col2, col3 = st.columns(3)

            with col1:
                check_mail_btn = st.button("🔍 Проверить почту", use_container_width=True, type="primary")

            with col2:
                if st.button("🔄 Мониторинг (5 мин)", use_container_width=True):
                    st.session_state.monitoring = True
                    st.info("Мониторинг запущен. Проверка каждые 5 минут.")

            with col3:
                if st.button("⏹️ Остановить", use_container_width=True):
                    st.session_state.monitoring = False
                    st.info("Мониторинг остановлен")

            # Placeholder для прогресса
            progress_placeholder = st.empty()
            results_placeholder = st.empty()

            if check_mail_btn:
                found = process_emails(scan_all=scan_all, progress_placeholder=progress_placeholder)

                progress_placeholder.empty()  # Очищаем прогресс

                if found:
                    with results_placeholder.container():
                        st.success(f"✅ Найдено {len(found)} новых договоров!")
                        for doc in found:
                            # Используем безопасную санитизацию
                            safe_subject = sanitize_html(doc.get('email_subject', 'Без темы'), max_length=100)
                            safe_from = sanitize_html(doc.get('email_from', ''), max_length=100)
                            safe_summary = sanitize_html(doc.get('summary', ''), max_length=150)
                            order_num = int(doc.get('order_number', 0))  # Только числа
                            st.markdown(f"""
                            <div class="contract-found">
                                <strong>№{order_num}</strong>: {safe_subject}<br>
                                📧 От: {safe_from}<br>
                                📝 {safe_summary}
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    results_placeholder.info("📭 Новых договоров не найдено")

            # Статус мониторинга
            if st.session_state.monitoring:
                st.warning("🔄 Мониторинг активен")
                if st.session_state.last_check:
                    st.text(f"Последняя проверка: {st.session_state.last_check.strftime('%H:%M:%S')}")

                # Автоматическая проверка
                time.sleep(1)  # Небольшая задержка для UI
                # В реальном приложении здесь будет polling с интервалом

    with tab2:
        st.header("📱 WhatsApp Мониторинг")
        st.markdown("**Автоматический мониторинг договоров из WhatsApp**")

        # Проверка Playwright
        if not PLAYWRIGHT_AVAILABLE:
            st.error("⚠️ Для работы с WhatsApp необходим Playwright")
            st.code("pip install playwright\nplaywright install chromium", language="bash")
            st.info("После установки перезапустите приложение")
        else:
            # Функция обработки документа из монитора
            def process_whatsapp_document(doc):
                """Callback для обработки документа из монитора."""
                try:
                    init_document_processor()
                    init_rag()

                    is_contract = doc.is_contract
                    confidence = 0.5 if is_contract else 0.0
                    contract_info = {}

                    # Deep classification with LLM
                    if st.session_state.document_processor and doc.text:
                        try:
                            is_contract, confidence = st.session_state.document_processor.is_contract(doc.text)
                            if is_contract:
                                contract_info = st.session_state.document_processor.extract_contract_info(doc.text)
                        except Exception as e:
                            logger.debug(f"Classification error: {e}")

                    if is_contract:
                        result = {
                            'order_number': st.session_state.order_number,
                            'email_id': doc.file_path or '',
                            'email_from': f'WhatsApp: {doc.sender}',
                            'email_subject': f'Чат: {doc.subject}',
                            'email_date': doc.received_at or datetime.now(),
                            'document_type': contract_info.get('document_type', 'Договор'),
                            'summary': contract_info.get('summary', doc.text[:150] if doc.text else doc.filename)[:200],
                            'parties': contract_info.get('parties', ''),
                            'amount': contract_info.get('amount', ''),
                            'responsible': doc.sender,
                            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'execution_period': contract_info.get('execution_period', ''),
                            'penalties': contract_info.get('penalties', ''),
                            'source': f'whatsapp:{doc.filename}',
                            'confidence': f'{confidence:.0%}'
                        }
                        st.session_state.processed_documents.append(result)
                        st.session_state.order_number += 1
                        st.session_state.whatsapp_stats['contracts'] = st.session_state.whatsapp_stats.get('contracts', 0) + 1

                    # Save document info
                    st.session_state.whatsapp_documents.append({
                        'filename': doc.filename,
                        'sender': doc.sender,
                        'chat': doc.subject,
                        'is_contract': is_contract,
                        'confidence': confidence
                    })
                    st.session_state.whatsapp_stats['documents'] = st.session_state.whatsapp_stats.get('documents', 0) + 1

                    if doc.file_path:
                        st.session_state.processed_whatsapp_files.add(doc.file_path)

                except Exception as e:
                    logger.error(f"Error processing WhatsApp document: {e}")

            def on_monitor_event(event):
                """Callback для событий монитора."""
                st.session_state.whatsapp_monitor_events.insert(0, {
                    'type': event.event_type,
                    'message': event.message,
                    'time': event.timestamp.strftime('%H:%M:%S')
                })
                # Keep only last 50 events
                st.session_state.whatsapp_monitor_events = st.session_state.whatsapp_monitor_events[:50]
                logger.info(f"[WhatsApp Monitor] {event.message}")

            # Статус мониторинга
            monitor = get_monitor()
            is_monitoring = bool(monitor and monitor.is_running)
            is_connected = bool(monitor and monitor.is_connected)

            col_status1, col_status2, col_status3 = st.columns(3)
            with col_status1:
                if is_monitoring:
                    if is_connected:
                        st.success("🟢 Мониторинг активен")
                    else:
                        st.warning("🟡 Подключение...")
                else:
                    st.info("🔴 Мониторинг выключен")
            with col_status2:
                stats = st.session_state.whatsapp_stats
                st.metric("📄 Документов", stats.get('documents', 0))
            with col_status3:
                st.metric("📋 Договоров", stats.get('contracts', 0))

            st.divider()

            # Инструкция
            with st.expander("📖 Как работает мониторинг", expanded=False):
                st.markdown("""
                ### Автоматический мониторинг WhatsApp:

                1. **Нажмите "Запустить мониторинг"** - откроется браузер
                2. **Отсканируйте QR-код** в WhatsApp на телефоне (если нужно):
                   - WhatsApp → Настройки → Связанные устройства → Привязать устройство
                3. **Мониторинг работает автоматически:**
                   - Проверяет чаты каждую минуту
                   - Находит новые документы (PDF, DOCX, XLSX)
                   - Скачивает и классифицирует их
                   - Добавляет договоры в результаты

                ⚠️ **Важно:**
                - Браузер должен оставаться открытым
                - Сессия сохраняется между перезапусками
                - Новые документы обрабатываются автоматически
                """)

            # Настройки мониторинга
            st.subheader("⚙️ Настройки мониторинга")
            col_opt1, col_opt2 = st.columns(2)
            with col_opt1:
                chat_limit = st.slider("Количество чатов для проверки", min_value=3, max_value=30, value=10, key="wa_chat_limit")
            with col_opt2:
                check_interval = st.slider("Интервал проверки (сек)", min_value=30, max_value=300, value=60, key="wa_interval")

            st.divider()

            # Кнопки управления
            col_btn1, col_btn2, col_btn3 = st.columns(3)

            with col_btn1:
                if st.button("▶️ Запустить мониторинг", use_container_width=True, type="primary",
                            disabled=is_monitoring, key="wa_start"):
                    try:
                        # Create monitor (subprocess-based)
                        monitor = create_monitor(
                            check_interval=check_interval,
                            chat_limit=chat_limit
                        )

                        # Add already processed files
                        for fp in st.session_state.processed_whatsapp_files:
                            monitor.add_processed_file(fp)

                        # Start monitoring subprocess
                        if monitor.start():
                            st.session_state.whatsapp_monitoring = True
                            st.success("✅ Мониторинг запущен! Откроется браузер с WhatsApp Web.")
                            st.info("📱 Если нужно - отсканируйте QR-код в браузере")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Не удалось запустить мониторинг")

                    except Exception as e:
                        st.error(f"❌ Ошибка запуска: {e}")
                        logger.error(f"Monitor start error: {e}")

            with col_btn2:
                if st.button("⏹️ Остановить мониторинг", use_container_width=True,
                            disabled=not is_monitoring, key="wa_stop"):
                    try:
                        stop_monitor()
                        st.session_state.whatsapp_monitoring = False
                        st.info("Мониторинг остановлен")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Ошибка остановки: {e}")

            with col_btn3:
                if st.button("🗑️ Очистить результаты", use_container_width=True, key="wa_clear"):
                    st.session_state.whatsapp_documents = []
                    st.session_state.whatsapp_stats = {'chats': 0, 'documents': 0, 'contracts': 0}
                    st.session_state.processed_whatsapp_files = set()
                    st.session_state.whatsapp_monitor_events = []
                    # Delete results file
                    results_file = Path("whatsapp_monitor_results.json")
                    if results_file.exists():
                        results_file.unlink()
                    st.rerun()

            # Если мониторинг активен - проверяем новые документы
            if is_monitoring and monitor:
                # Poll for new documents
                new_docs = monitor.get_new_documents()

                for doc in new_docs:
                    # Process each new document
                    try:
                        init_document_processor()
                        init_rag()

                        is_contract = doc.get('is_contract', False)
                        confidence = 0.5 if is_contract else 0.0
                        contract_info = {}
                        text = doc.get('text', '')

                        # Deep classification with LLM
                        if st.session_state.document_processor and text:
                            try:
                                is_contract, confidence = st.session_state.document_processor.is_contract(text)
                                if is_contract:
                                    contract_info = st.session_state.document_processor.extract_contract_info(text)
                            except Exception as e:
                                logger.debug(f"Classification error: {e}")

                        filename = doc.get('filename', 'unknown')
                        sender = doc.get('sender', 'Unknown')
                        chat_name = doc.get('chat_name', 'Unknown')
                        file_path = doc.get('file_path', '')

                        if is_contract:
                            result = {
                                'order_number': st.session_state.order_number,
                                'email_id': file_path,
                                'email_from': f'WhatsApp: {sender}',
                                'email_subject': f'Чат: {chat_name}',
                                'email_date': datetime.now(),
                                'document_type': contract_info.get('document_type', 'Договор'),
                                'summary': contract_info.get('summary', text[:150] if text else filename)[:200],
                                'parties': contract_info.get('parties', ''),
                                'amount': contract_info.get('amount', ''),
                                'responsible': sender,
                                'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'execution_period': contract_info.get('execution_period', ''),
                                'penalties': contract_info.get('penalties', ''),
                                'source': f'whatsapp:{filename}',
                                'confidence': f'{confidence:.0%}'
                            }
                            st.session_state.processed_documents.append(result)
                            st.session_state.order_number += 1
                            st.session_state.whatsapp_stats['contracts'] = st.session_state.whatsapp_stats.get('contracts', 0) + 1

                        # Save document info
                        st.session_state.whatsapp_documents.append({
                            'filename': filename,
                            'sender': sender,
                            'chat': chat_name,
                            'is_contract': is_contract,
                            'confidence': confidence
                        })
                        st.session_state.whatsapp_stats['documents'] = st.session_state.whatsapp_stats.get('documents', 0) + 1

                        if file_path:
                            st.session_state.processed_whatsapp_files.add(file_path)

                        # Add event
                        st.session_state.whatsapp_monitor_events.insert(0, {
                            'type': 'document_found',
                            'message': f"Найден: {filename}",
                            'time': datetime.now().strftime('%H:%M:%S')
                        })

                        logger.info(f"Processed WhatsApp document: {filename}")

                    except Exception as e:
                        logger.error(f"Error processing document: {e}")

                # Show stats
                st.divider()
                status = monitor.get_status()
                status_text = {
                    'connecting': '🟡 Подключение...',
                    'monitoring': '🟢 Мониторинг активен',
                    'error': '🔴 Ошибка',
                    'stopped': '⚫ Остановлен'
                }.get(status, f'❓ {status}')

                col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                with col_stat1:
                    st.metric("📊 Статус", status_text)
                with col_stat2:
                    st.metric("🔍 Проверок", monitor.stats.get('checks_count', 0))
                with col_stat3:
                    last_check = monitor.stats.get('last_check')
                    if last_check:
                        st.metric("⏱️ Последняя", last_check.strftime('%H:%M:%S'))
                    else:
                        st.metric("⏱️ Последняя", "-")
                with col_stat4:
                    st.metric("📥 Найдено", monitor.stats.get('documents_found', 0))

                # Auto-refresh while monitoring
                if new_docs:
                    st.rerun()
                else:
                    time.sleep(3)
                    st.rerun()

            # События монитора
            st.divider()
            with st.expander("📋 События мониторинга", expanded=is_monitoring):
                events = st.session_state.whatsapp_monitor_events
                if events:
                    for event in events[:20]:
                        icon = "📄" if event['type'] == 'document_found' else \
                               "✅" if event['type'] == 'document_processed' else \
                               "❌" if event['type'] == 'error' else "ℹ️"
                        st.text(f"{event['time']} {icon} {event['message']}")
                else:
                    st.info("События появятся после запуска мониторинга")

            # Логи
            with st.expander("📋 Логи обработки", expanded=False):
                logs = whatsapp_log_handler.get_logs()
                if logs:
                    log_text = "\n".join(logs[:100])
                    st.text_area("Логи", value=log_text, height=200, disabled=True, label_visibility="collapsed")
                    if st.button("🗑️ Очистить логи", key="wa_clear_logs"):
                        whatsapp_log_handler.clear_logs()
                        st.rerun()
                else:
                    st.info("Логи появятся после начала мониторинга")

            # Результаты
            if st.session_state.whatsapp_documents:
                st.divider()
                st.subheader("📄 Найденные документы")

                show_contracts_only = st.checkbox("Показать только договоры", value=False, key="wa_filter_contracts")

                docs_to_show = st.session_state.whatsapp_documents
                if show_contracts_only:
                    docs_to_show = [d for d in docs_to_show if d.get('is_contract')]

                for doc in docs_to_show[-20:]:
                    contract_badge = "📋 ДОГОВОР" if doc.get('is_contract') else "📄"
                    conf = doc.get('confidence', 0)
                    conf_str = f" ({conf:.0%})" if conf > 0 else ""

                    st.markdown(f"""
                    <div class="{'contract-found' if doc.get('is_contract') else 'info-box'}">
                        <strong>{contract_badge} {doc.get('filename', 'Без имени')}</strong>{conf_str}<br>
                        👤 От: {doc.get('sender', 'Неизвестно')}<br>
                        💬 Чат: {doc.get('chat', 'Неизвестно')}
                    </div>
                    """, unsafe_allow_html=True)

        # Резервный вариант - экспорт чатов
        st.divider()
        with st.expander("📂 Альтернатива: загрузка экспортированного чата", expanded=False):
            st.markdown("Если автоматический режим недоступен, можно загрузить экспортированный чат:")

            uploaded_file = st.file_uploader(
                "Выберите .txt файл экспорта WhatsApp",
                type=['txt'],
                help="Файл экспорта чата из WhatsApp",
                key="whatsapp_export_file"
            )

            if uploaded_file is not None:
                import tempfile
                with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
                    f.write(uploaded_file.getvalue())
                    temp_path = f.name

                try:
                    with st.spinner("📱 Парсинг чата..."):
                        chat = st.session_state.whatsapp_agent.parse_exported_chat(temp_path)

                    st.success(f"✅ Загружено {len(chat.messages)} сообщений")
                    contract_msgs = [m for m in chat.messages if m.is_contract]
                    st.info(f"📋 Найдено {len(contract_msgs)} сообщений с договорами")

                except Exception as e:
                    st.error(f"Ошибка: {e}")
                finally:
                    import os
                    os.unlink(temp_path)

    with tab3:
        st.header("🔄 Фоновый мониторинг почты")
        st.markdown("**Мониторинг работает 24/7, даже когда браузер закрыт**")

        # Проверка доступности Celery
        try:
            from utils.storage import MonitorStorage
            storage = MonitorStorage()
            celery_available = True
        except Exception as e:
            celery_available = False
            st.error(f"⚠️ Фоновый мониторинг недоступен: {e}")

        if celery_available:
            # Статистика
            stats = storage.get_stats()

            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.metric("🔄 Активных мониторов", stats.get('active_monitors', 0))
            with col_stat2:
                st.metric("📄 Всего документов", stats.get('total_documents', 0))
            with col_stat3:
                st.metric("📥 За 24 часа", stats.get('documents_24h', 0))

            st.divider()

            # Форма добавления мониторинга
            st.subheader("➕ Добавить email для мониторинга")

            with st.form("add_monitor_form"):
                monitor_email = st.text_input(
                    "Email адрес",
                    placeholder="example@gmail.com",
                    help="Email который нужно мониторить 24/7"
                )
                monitor_password = st.text_input(
                    "Пароль приложения",
                    type="password",
                    help="App Password для Gmail/Yandex"
                )
                monitor_scan_all = st.checkbox(
                    "Сканировать все письма",
                    value=True,
                    help="Если выключено - только новые непрочитанные"
                )

                submitted = st.form_submit_button("🚀 Запустить мониторинг", type="primary")

                if submitted:
                    if not monitor_email or not monitor_password:
                        st.error("Заполните email и пароль")
                    else:
                        try:
                            from tasks.email_tasks import start_email_monitoring
                            # Запускаем задачу через Celery
                            start_email_monitoring.delay(
                                email_address=monitor_email,
                                password=monitor_password,
                                scan_all=monitor_scan_all
                            )

                            st.success(f"✅ Мониторинг запущен для {monitor_email}")
                            st.info("📧 Проверка будет выполняться каждые 5 минут в фоне")
                            time.sleep(1)
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ Ошибка запуска: {e}")
                            logger.error(f"Failed to start monitoring: {e}")

            st.divider()

            # Список активных мониторов
            st.subheader("📋 Активные мониторы")

            configs = storage.get_all_active_configs()

            if configs:
                for config in configs:
                    with st.container():
                        col1, col2, col3 = st.columns([3, 2, 1])

                        with col1:
                            st.markdown(f"**📧 {config.email_address}**")
                            if config.last_check:
                                st.caption(f"Последняя проверка: {config.last_check.strftime('%d.%m.%Y %H:%M')}")
                            else:
                                st.caption("Ещё не проверялось")

                        with col2:
                            docs_count = storage.get_documents_count(config.email_address)
                            st.metric("Документов", docs_count)

                        with col3:
                            if st.button("⏹️ Стоп", key=f"stop_{config.email_address}"):
                                try:
                                    from tasks.email_tasks import stop_email_monitoring
                                    stop_email_monitoring.delay(config.email_address)
                                    st.success("Мониторинг остановлен")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")

                        st.divider()
            else:
                st.info("📭 Нет активных мониторов. Добавьте email выше.")

            # Последние найденные документы
            st.subheader("📄 Последние найденные документы")

            docs = storage.get_documents(limit=10)

            if docs:
                for doc in docs:
                    with st.expander(f"📋 {doc.document_type}: {doc.email_subject[:50]}...", expanded=False):
                        st.markdown(f"**От:** {doc.email_from}")
                        st.markdown(f"**Дата:** {doc.email_date.strftime('%d.%m.%Y') if doc.email_date else 'N/A'}")
                        st.markdown(f"**Тип:** {doc.document_type}")
                        st.markdown(f"**Описание:** {doc.summary}")
                        if doc.parties:
                            st.markdown(f"**Стороны:** {doc.parties}")
                        if doc.amount:
                            st.markdown(f"**Сумма:** {doc.amount}")
            else:
                st.info("📭 Документы появятся после первой проверки")

        # Инструкция
        with st.expander("📖 Как работает фоновый мониторинг", expanded=False):
            st.markdown("""
            ### Фоновый мониторинг 24/7

            **Преимущества:**
            - Работает даже когда браузер закрыт
            - Проверяет почту каждые 5 минут
            - Автоматически находит и обрабатывает договоры
            - Сохраняет результаты в базу данных

            **Как это работает:**
            1. Вы добавляете email для мониторинга
            2. Celery worker проверяет почту в фоне
            3. Найденные договоры обрабатываются LLM
            4. Результаты сохраняются и доступны в любое время

            **Архитектура:**
            ```
            [Redis] ← [Celery Beat] → [Celery Worker] → [Email + LLM]
                                              ↓
                                        [SQLite DB]
                                              ↓
                                     [Streamlit UI]
            ```
            """)

    with tab4:
        st.header("📋 Обработанные документы")

        if st.session_state.processed_documents:
            # Показываем таблицу
            df = create_excel_dataframe()
            st.dataframe(df, use_container_width=True)

            # Экспорт в Excel
            st.divider()

            # Кнопки экспорта
            st.subheader("📥 Экспорт")
            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                excel_data = export_to_excel()
                if excel_data:
                    st.download_button(
                        label="📥 Скачать ВСЕ в один Excel",
                        data=excel_data,
                        file_name=f"contracts_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            with col2:
                st.metric("Всего документов", len(st.session_state.processed_documents))

            with col3:
                if st.button("🗑️ Очистить всё", use_container_width=True):
                    st.session_state.processed_documents = []
                    st.session_state.processed_email_ids = set()
                    st.session_state.order_number = 1
                    st.rerun()

            # Отдельные файлы для каждого договора
            st.divider()
            st.subheader("📄 Скачать отдельные договоры")

            for i, doc in enumerate(st.session_state.processed_documents):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    subject = doc.get('email_subject', 'Без темы')[:50]
                    st.text(f"№{doc.get('order_number', i+1)}: {subject}")
                with col_b:
                    # Создаём отдельный Excel для этого договора
                    single_df = pd.DataFrame([doc])
                    single_df = single_df.rename(columns={
                        'order_number': '№ п/п',
                        'email_date': 'Дата входящего',
                        'summary': 'Описание документа',
                        'email_from': 'Email отправителя',
                        'responsible': 'Ответственные',
                        'processed_at': 'Дата обработки',
                        'document_type': 'Тип документа',
                        'email_subject': 'Тема письма',
                        'parties': 'Стороны договора',
                        'amount': 'Сумма'
                    })

                    # Убираем timezone
                    for col in single_df.columns:
                        if single_df[col].dtype == 'datetime64[ns, UTC]' or str(single_df[col].dtype).startswith('datetime'):
                            try:
                                single_df[col] = pd.to_datetime(single_df[col]).dt.tz_localize(None)
                            except (TypeError, ValueError):
                                single_df[col] = single_df[col].astype(str)
                        if single_df[col].apply(lambda x: hasattr(x, 'tzinfo') and getattr(x, 'tzinfo', None) is not None).any():
                            single_df[col] = single_df[col].apply(lambda x: x.replace(tzinfo=None) if hasattr(x, 'replace') and hasattr(x, 'tzinfo') else x)

                    single_output = io.BytesIO()
                    with pd.ExcelWriter(single_output, engine='openpyxl') as writer:
                        single_df.to_excel(writer, sheet_name='Договор', index=False)

                    order_num = doc.get('order_number', i+1)
                    st.download_button(
                        label="📥",
                        data=single_output.getvalue(),
                        file_name=f"contract_{order_num}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_{i}"
                    )
        else:
            st.info("📭 Пока нет обработанных документов")

    with tab5:
        st.header("📖 Справка")

        st.markdown("""
        ### 🎯 О приложении

        **Document Processing Agent** - интеллектуальный агент для автоматической обработки
        юридических документов и договоров из электронной почты и WhatsApp.

        ### 📧 Поддерживаемые почтовые сервисы

        | Сервис | IMAP сервер |
        |--------|-------------|
        | Gmail | imap.gmail.com |
        | Yandex | imap.yandex.ru |
        | Mail.ru | imap.mail.ru |
        | Outlook | outlook.office365.com |

        ### 📱 WhatsApp

        **Два режима работы:**

        | Режим | Описание |
        |-------|----------|
        | 📂 Экспорт чата | Загрузите .txt файл экспорта из WhatsApp |
        | 🌐 WhatsApp Web (Playwright) | Автоматическое сканирование чатов |

        **Автоматический режим (Playwright):**
        1. Нажмите "Подключиться к WhatsApp"
        2. Отсканируйте QR-код (только первый раз)
        3. Нажмите "Сканировать чаты"
        4. Система автоматически найдёт и скачает документы

        **Как экспортировать чат вручную:**
        1. Откройте чат → ⋮ → Ещё → Экспорт чата
        2. Выберите "Без медиафайлов"
        3. Загрузите .txt файл в приложение

        ### 🔐 Настройка Gmail

        Для Gmail необходимо создать **App Password**:
        1. Перейдите в [Google Account Security](https://myaccount.google.com/security)
        2. Включите 2-факторную аутентификацию
        3. Создайте App Password: Security → App passwords
        4. Используйте сгенерированный 16-значный пароль

        ### 🔐 Настройка Yandex

        1. Перейдите в [Настройки безопасности](https://passport.yandex.ru/profile)
        2. Создайте пароль приложения

        ### 📊 Извлекаемая информация

        | Поле | Описание |
        |------|----------|
        | Тип документа | Договор аренды, поставки, подряда и т.д. |
        | Стороны | Участники договора |
        | Сумма | Сумма договора |
        | Дата | Дата заключения |
        | Срок действия | До какой даты действует |
        | **Срок исполнения** | Когда нужно выполнить обязательства |
        | **Ответственность** | Пени, неустойки, штрафы |
        | Ответственные | ФИО ответственных лиц |

        ### ⚙️ RAG Система

        Используется RAG система с:
        - **Векторный поиск**: ChromaDB + sentence-transformers
        - **Автоматическое обучение**: Система запоминает обработанные договоры
        - **Pre-Retrieval**: Расширение запросов юридическими синонимами
        - **Post-Retrieval**: Переранжирование по релевантности

        Шаблоны договоров загружаются из папки `templates/`.
        """)


if __name__ == "__main__":
    main()

