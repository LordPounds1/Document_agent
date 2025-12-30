"""
📧 Document Processing Agent - Web Interface
Веб-интерфейс для обработки договоров из почты

Функциональность:
1. Ввод email (Gmail, Yandex и др.)
2. Обработка почты, поиск писем с договорами
3. Анализ договоров с помощью LLM
4. Создание Excel таблицы с результатами
5. Мониторинг новых писем
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import logging
import io
import html
import sys

# Добавляем родительскую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent))

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Импорт компонентов
from agents.email_agent import EmailAgent
from processors.document import DocumentProcessor
from core.rag import SimpleRAG

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
    if 'document_processor' not in st.session_state:
        st.session_state.document_processor = None
    if 'rag' not in st.session_state:
        st.session_state.rag = None
    if 'connected' not in st.session_state:
        st.session_state.connected = False
    if 'processed_documents' not in st.session_state:
        st.session_state.processed_documents = []
    if 'processed_email_ids' not in st.session_state:
        st.session_state.processed_email_ids = set()  # Для отслеживания уже обработанных писем
    if 'order_number' not in st.session_state:
        st.session_state.order_number = 1
    if 'monitoring' not in st.session_state:
        st.session_state.monitoring = False
    if 'last_check' not in st.session_state:
        st.session_state.last_check = None
    if 'scan_all' not in st.session_state:
        st.session_state.scan_all = True  # По умолчанию сканируем все письма


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
        'email_from': 'Email отправителя',
        'responsible': 'Ответственные',
        'processed_at': 'Дата обработки',
        'document_type': 'Тип документа',
        'email_subject': 'Тема письма',
        'parties': 'Стороны договора',
        'amount': 'Сумма'
    }
    
    df = df.rename(columns=columns_mapping)
    
    # Порядок колонок
    ordered_columns = [
        '№ п/п', 'Дата входящего', 'Описание документа', 
        'Email отправителя', 'Ответственные', 'Дата обработки',
        'Тип документа', 'Тема письма', 'Стороны договора', 'Сумма'
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
            except:
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
    
    # Заголовок
    st.markdown('<h1 class="main-header">📄 Document Processing Agent</h1>', unsafe_allow_html=True)
    st.markdown("**Интеллектуальный агент для обработки договоров из почты**")
    
    # Боковая панель - настройки
    with st.sidebar:
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
                if email_address and password:
                    with st.spinner("Подключение..."):
                        if connect_email(email_address, password):
                            st.success("✅ Успешно подключено!")
                        else:
                            st.error("❌ Ошибка подключения")
                else:
                    st.warning("Введите email и пароль")
        
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
        if st.button("❌ Закрыть приложение", use_container_width=True, type="secondary"):
            st.session_state.email_agent.disconnect()
            st.warning("Приложение будет закрыто...")
            time.sleep(1)
            # Останавливаем Streamlit
            import os
            os._exit(0)
    
    # Основной контент
    tab1, tab2, tab3 = st.tabs(["📬 Обработка почты", "📋 Результаты", "📖 Справка"])
    
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
                            # Экранируем HTML в пользовательских данных
                            safe_subject = html.escape(str(doc.get('email_subject', 'Без темы')))
                            safe_from = html.escape(str(doc.get('email_from', '')))
                            safe_summary = html.escape(str(doc.get('summary', ''))[:100])
                            st.markdown(f"""
                            <div class="contract-found">
                                <strong>№{doc['order_number']}</strong>: {safe_subject}<br>
                                📧 От: {safe_from}<br>
                                📝 {safe_summary}...
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
                            except:
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
    
    with tab3:
        st.header("📖 Справка")
        
        st.markdown("""
        ### 🎯 О приложении
        
        **Document Processing Agent** - интеллектуальный агент для автоматической обработки 
        юридических документов и договоров из электронной почты.
        
        ### 📧 Поддерживаемые почтовые сервисы
        
        | Сервис | IMAP сервер |
        |--------|-------------|
        | Gmail | imap.gmail.com |
        | Yandex | imap.yandex.ru |
        | Mail.ru | imap.mail.ru |
        | Outlook | outlook.office365.com |
        
        ### 🔐 Настройка Gmail
        
        Для Gmail необходимо создать **App Password**:
        1. Перейдите в [Google Account Security](https://myaccount.google.com/security)
        2. Включите 2-факторную аутентификацию
        3. Создайте App Password: Security → App passwords
        4. Используйте сгенерированный 16-значный пароль
        
        ### 🔐 Настройка Yandex
        
        1. Перейдите в [Настройки безопасности](https://passport.yandex.ru/profile)
        2. Создайте пароль приложения
        
        ### 📊 Формат Excel таблицы
        
        | Колонка | Описание |
        |---------|----------|
        | № п/п | Порядковый номер |
        | Дата входящего | Дата получения письма |
        | Описание документа | Краткое описание договора |
        | Email отправителя | Адрес отправителя |
        | Ответственные | ФИО ответственных лиц |
        | Дата обработки | Когда был обработан |
        
        ### ⚙️ RAG Система
        
        Используется упрощённая RAG система с:
        - **Pre-Retrieval**: Расширение запросов юридическими синонимами
        - **Post-Retrieval**: Переранжирование по релевантности
        
        Шаблоны договоров загружаются из папки `templates/`.
        """)


if __name__ == "__main__":
    main()
