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

import html
import io
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import streamlit as st

# Добавляем родительскую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent))

# Security imports
from utils.security import (
    validate_email,
    validate_password,
    sanitize_html,
    sanitize_filename,
    login_rate_limiter,
)
from utils.auth import require_auth, show_user_menu, logout

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
        import threading
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
        except Exception:
            # Игнорируем ошибки в handler, чтобы не ломать приложение
            pass
    
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

# Импорт компонентов
from agents.email_agent import EmailAgent
from agents.whatsapp_agent import WhatsAppAgent
from processors.document import DocumentProcessor
from core.rag import SimpleRAG

# Импорт WhatsApp Playwright модуля (subprocess версия для Streamlit на Windows)
import subprocess
import json

try:
    import playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    SubprocessDocument = None

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
                if 'email_date' in result and hasattr(result['email_date'], 'tzinfo'):
                    if result['email_date'].tzinfo is not None:
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


def process_whatsapp_text(text: str, msg, source: str) -> Optional[Dict]:
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
    tab1, tab2, tab3, tab4 = st.tabs(["📬 Обработка почты", "📱 WhatsApp", "📋 Результаты", "📖 Справка"])
    
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
        st.header("📱 WhatsApp (Playwright)")
        st.markdown("**Автоматический поиск и обработка договоров из WhatsApp**")
        
        # Проверка Playwright
        if not PLAYWRIGHT_AVAILABLE:
            st.error("⚠️ Для работы с WhatsApp необходим Playwright")
            st.code("pip install playwright\nplaywright install chromium", language="bash")
            st.info("После установки перезапустите приложение")
        else:
            # Статус
            col_status1, col_status2 = st.columns(2)
            with col_status1:
                if st.session_state.whatsapp_processing:
                    st.info("⏳ Идёт сканирование...")
                else:
                    stats = st.session_state.whatsapp_stats
                    if stats.get('documents', 0) > 0:
                        st.success(f"✅ Найдено {stats.get('documents', 0)} документов")
                    else:
                        st.warning("🔴 Документы не загружены")
            with col_status2:
                stats = st.session_state.whatsapp_stats
                st.metric("📋 Договоров", stats.get('contracts', 0))
            
            st.divider()
            
            # Инструкция
            with st.expander("📖 Как это работает", expanded=False):
                st.markdown("""
                ### Автоматический поиск документов:
                
                1. **Нажмите "Сканировать WhatsApp"** - откроется браузер
                2. **Отсканируйте QR-код** в WhatsApp на телефоне (если нужно):
                   - WhatsApp → Настройки → Связанные устройства → Привязать устройство
                3. **Дождитесь завершения** - система автоматически:
                   - Откроет каждый чат
                   - Найдёт документы (PDF, DOCX, XLSX)
                   - Скачает их и классифицирует
                
                ⚠️ **Важно:** 
                - Сессия сохраняется - при повторном запуске QR-код обычно не нужен
                - Сканирование занимает 2-5 минут в зависимости от количества чатов
                """)
            
            # Настройки сканирования
            st.subheader("⚙️ Параметры сканирования")
            col_opt1, col_opt2 = st.columns(2)
            with col_opt1:
                chat_limit = st.slider("Количество чатов", min_value=3, max_value=50, value=10, key="wa_chat_limit")
            with col_opt2:
                doc_limit = st.slider("Макс. документов", min_value=5, max_value=100, value=30, key="wa_doc_limit")
            
            st.divider()
            
            # Кнопка сканирования
            col_scan1, col_scan2 = st.columns(2)
            
            with col_scan1:
                if st.button("🔍 Сканировать WhatsApp", use_container_width=True, type="primary",
                            disabled=st.session_state.whatsapp_processing, key="wa_scan"):
                    st.session_state.whatsapp_processing = True
                    
                    progress_bar = st.progress(0, text="Запуск браузера...")
                    status_text = st.empty()
                    
                    try:
                        status_text.info("🚀 Запускается браузер... Ожидайте появления окна с WhatsApp Web")
                        progress_bar.progress(0.05)
                        
                        # Путь к результатам
                        results_file = Path("whatsapp_scan_results.json")
                        if results_file.exists():
                            results_file.unlink()
                        
                        # Запускаем скрипт сканирования как отдельный процесс
                        # Используем тот же Python что и Streamlit
                        cmd = [
                            sys.executable, "-m", "whatsapp.run_scan",
                            "--output", str(results_file),
                            "--chats", str(chat_limit),
                            "--docs", str(doc_limit),
                            "--timeout", "120"
                        ]
                        
                        logger.info(f"Starting WhatsApp scan: {' '.join(cmd)}")
                        
                        # Запускаем процесс
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=str(Path(__file__).parent.parent)
                        )
                        
                        status_text.info("📱 Если нужно - отсканируйте QR-код в открывшемся браузере")
                        progress_bar.progress(0.1, text="Ожидание входа в WhatsApp...")
                        
                        # Ждём завершения процесса с таймаутом
                        max_wait = 600  # 10 минут максимум
                        start_time = time.time()
                        
                        while process.poll() is None:
                            elapsed = time.time() - start_time
                            if elapsed > max_wait:
                                process.terminate()
                                st.error("❌ Таймаут сканирования (10 минут)")
                                break
                            
                            # Обновляем прогресс
                            progress = min(0.9, 0.1 + (elapsed / max_wait) * 0.8)
                            progress_bar.progress(progress, text=f"Сканирование... ({int(elapsed)}с)")
                            
                            # Читаем вывод процесса для логов
                            try:
                                line = process.stdout.readline()
                                if line:
                                    line = line.strip()
                                    if line:
                                        logger.info(line)
                                        # Показываем ключевые события
                                        if "Connected" in line or "подключ" in line.lower():
                                            status_text.success("✅ Подключено к WhatsApp!")
                                        elif "Scanning" in line or "сканиров" in line.lower():
                                            status_text.info("🔍 Сканирование чатов...")
                                        elif "Found" in line or "найден" in line.lower():
                                            status_text.info(f"📄 {line}")
                            except:
                                pass
                            
                            time.sleep(0.5)
                        
                        # Читаем результаты
                        if results_file.exists():
                            try:
                                result_data = json.loads(results_file.read_text(encoding='utf-8'))
                                documents = result_data.get('documents', [])
                                
                                progress_bar.progress(0.95, text="Классификация документов...")
                                status_text.text("🤖 Анализ документов с помощью LLM...")
                                
                                init_document_processor()
                                init_rag()
                                
                                # Классификация
                                contracts_found = 0
                                for doc in documents:
                                    file_path = doc.get('file_path', '')
                                    if file_path and file_path in st.session_state.processed_whatsapp_files:
                                        continue
                                    
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
                                    
                                    if is_contract:
                                        contracts_found += 1
                                        
                                        # Add to results
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
                                        if file_path:
                                            st.session_state.processed_whatsapp_files.add(file_path)
                                    
                                    # Save document info
                                    st.session_state.whatsapp_documents.append({
                                        'filename': filename,
                                        'sender': sender,
                                        'chat': chat_name,
                                        'is_contract': is_contract,
                                        'confidence': confidence
                                    })
                                
                                # Update stats
                                st.session_state.whatsapp_stats = {
                                    'chats': chat_limit,
                                    'documents': len(documents),
                                    'contracts': contracts_found
                                }
                                
                                progress_bar.progress(1.0, text="Готово!")
                                status_text.empty()
                                
                                if len(documents) == 0:
                                    st.warning("📭 Документы не найдены. Убедитесь что в чатах есть PDF/DOC/XLSX файлы.")
                                else:
                                    st.success(f"✅ Найдено {len(documents)} документов, из них {contracts_found} договоров!")
                                
                            except json.JSONDecodeError as e:
                                st.error(f"❌ Ошибка чтения результатов: {e}")
                        else:
                            st.error("❌ Результаты сканирования не найдены. Возможно, произошла ошибка.")
                        
                        st.session_state.whatsapp_processing = False
                        
                    except Exception as e:
                        st.error(f"❌ Ошибка сканирования: {e}")
                        logger.error(f"Ошибка сканирования WhatsApp: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        st.session_state.whatsapp_processing = False
            
            with col_scan2:
                if st.button("🗑️ Очистить результаты", use_container_width=True, key="wa_clear"):
                    st.session_state.whatsapp_documents = []
                    st.session_state.whatsapp_stats = {'chats': 0, 'documents': 0, 'contracts': 0}
                    st.session_state.processed_whatsapp_files = set()
                    st.rerun()
            
            # Показываем логи
            st.divider()
            with st.expander("📋 Логи обработки", expanded=True):
                logs = whatsapp_log_handler.get_logs()
                if logs:
                    log_text = "\n".join(logs[:100])
                    st.text_area("Логи", value=log_text, height=300, disabled=True, label_visibility="collapsed")
                    if st.button("🗑️ Очистить логи", key="wa_clear_logs"):
                        whatsapp_log_handler.clear_logs()
                        st.rerun()
                else:
                    st.info("Логи появятся после начала сканирования")
            
            # Результаты сканирования
            if st.session_state.whatsapp_documents:
                st.divider()
                st.subheader("📄 Найденные документы")
                
                # Фильтр
                show_contracts_only = st.checkbox("Показать только договоры", value=False, key="wa_filter_contracts")
                
                docs_to_show = st.session_state.whatsapp_documents
                if show_contracts_only:
                    docs_to_show = [d for d in docs_to_show if d.get('is_contract')]
                
                for doc in docs_to_show[-20:]:  # Last 20
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
    
    with tab4:
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

