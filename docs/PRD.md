# 📋 Product Requirements Document (PRD)

## Document Processing Agent

**Версия:** 1.0  
**Дата:** Январь 2026  
**Статус:** В разработке  

---

## 📌 1. Обзор продукта

### 1.1 Описание

**Document Processing Agent** — интеллектуальная система для автоматической обработки юридических документов из электронной почты с использованием локальной LLM и технологии RAG (Retrieval-Augmented Generation).

### 1.2 Целевая аудитория

| Сегмент | Описание | Потребность |
|---------|----------|-------------|
| Юридические отделы | Компании с большим документооборотом | Автоматизация входящих договоров |
| Малый бизнес | ИП и небольшие компании | Обработка договоров без юриста |
| Бухгалтерии | Подготовка документов для учёта | Структурирование данных |

### 1.3 Проблема

Ручная обработка входящих договоров занимает 15-30 минут на документ:
- Поиск писем с вложениями
- Открытие и чтение документов
- Извлечение ключевой информации
- Занесение в таблицы

### 1.4 Решение

Автоматизированный агент, который:
1. Подключается к почте (IMAP)
2. Находит письма с договорами
3. Извлекает информацию с помощью LLM
4. Формирует структурированный отчёт

---

## 🎯 2. Цели и метрики

### 2.1 Бизнес-цели

| Цель | Метрика | Целевое значение |
|------|---------|------------------|
| Экономия времени | Минуты на документ | < 1 мин (было 15-30) |
| Точность извлечения | Accuracy | > 85% |
| Покрытие форматов | Поддерживаемые форматы | DOCX, PDF, TXT |
| Приватность | Данные на сервере | 100% локально |

### 2.2 Технические метрики

| Метрика | Целевое значение |
|---------|------------------|
| Время обработки письма | < 30 сек |
| Uptime | > 99% |
| Latency LLM | < 10 сек |
| Memory usage | < 12 GB RAM |

### 2.3 Критерии успеха MVP

- [ ] Подключение к Gmail, Yandex, Mail.ru, Outlook
- [ ] Извлечение данных из DOCX и PDF
- [ ] Формирование Excel отчёта
- [ ] Веб-интерфейс для пользователя
- [ ] Работа без интернета (локальная LLM)

---

## 🛠 3. Функциональные требования

### 3.1 Core Features (MVP)

#### FR-1: Подключение к почте
- **Описание:** Пользователь вводит email и пароль, система подключается по IMAP
- **Провайдеры:** Gmail, Yandex, Mail.ru, Outlook
- **Безопасность:** Пароли не сохраняются, используются App Passwords
- **Приоритет:** P0 (критично)

#### FR-2: Поиск договоров
- **Описание:** Система находит письма с вложениями-договорами
- **Критерии договора:** Ключевые слова, структура документа
- **Форматы:** .docx, .pdf, .txt
- **Приоритет:** P0

#### FR-3: Анализ с LLM
- **Описание:** Локальная модель извлекает структурированные данные
- **Извлекаемые поля:**
  - Тип документа
  - Стороны договора
  - Предмет договора
  - Сумма
  - Сроки
  - Ответственные лица
- **Приоритет:** P0

#### FR-4: Excel отчёт
- **Описание:** Формирование таблицы с результатами
- **Формат:** .xlsx (Microsoft Excel)
- **Функции:** Скачивание, просмотр в UI
- **Приоритет:** P0

#### FR-5: Мониторинг
- **Описание:** Периодическая проверка новых писем
- **Интервал:** Настраиваемый (по умолчанию 5 мин)
- **Приоритет:** P1

### 3.2 Security Features

#### FR-6: Аутентификация
- **Описание:** Вход в систему с логином/паролем
- **Хранение:** PBKDF2 хэширование
- **Блокировка:** После 5 неудачных попыток
- **Приоритет:** P0

#### FR-7: SSL/HTTPS
- **Описание:** Шифрование трафика
- **Сертификаты:** Let's Encrypt
- **Приоритет:** P0 (для продакшена)

#### FR-8: Шифрование шаблонов
- **Описание:** AES-256 шифрование конфиденциальных документов
- **Алгоритм:** Fernet (cryptography library)
- **Приоритет:** P1

### 3.3 Future Features (Post-MVP)

| Feature | Описание | Приоритет |
|---------|----------|-----------|
| OCR | Обработка сканированных документов | P2 |
| Telegram бот | Уведомления о новых договорах | P2 |
| CRM интеграция | Bitrix24, AmoCRM | P3 |
| Мультиязычность | EN, DE, KZ | P3 |
| Ручная коррекция | Редактирование извлечённых данных | P2 |

---

## 📐 4. Нефункциональные требования

### 4.1 Производительность

| Требование | Значение |
|------------|----------|
| Время загрузки UI | < 3 сек |
| Время обработки документа | < 30 сек |
| Одновременные пользователи | 1-5 (single instance) |
| Max размер вложения | 50 MB |

### 4.2 Надёжность

| Требование | Значение |
|------------|----------|
| Uptime | 99% |
| Recovery time | < 5 мин (docker restart) |
| Data durability | Локальные файлы + бэкапы |

### 4.3 Безопасность

| Требование | Реализация |
|------------|------------|
| Аутентификация | Username/password с хэшированием |
| Авторизация | Single-user / admin only |
| Encryption in transit | HTTPS (TLS 1.2+) |
| Encryption at rest | Fernet для шаблонов |
| Secrets management | Environment variables |

### 4.4 Совместимость

| Компонент | Требования |
|-----------|------------|
| Python | 3.10+ |
| Docker | 20.10+ |
| Браузер | Chrome 90+, Firefox 88+, Safari 14+ |
| ОС сервера | Ubuntu 22.04, Debian 12 |

---

## 🏗 5. Архитектура

### 5.1 Компоненты

```
┌─────────────────────────────────────────────────────────┐
│                      Nginx (HTTPS)                       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Streamlit UI (8501)                    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ Email Agent │  │ RAG Pipeline│  │ Document        │  │
│  │ (IMAP)      │  │ (Retrieval) │  │ Processor       │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│         │                │                  │            │
│         ▼                ▼                  ▼            │
│  ┌─────────────────────────────────────────────────────┐│
│  │              Local LLM (llama-cpp-python)           ││
│  │              Model: Saiga 7B (GGUF)                 ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   File System                            │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌───────────┐  │
│  │ models/ │  │templates/│  │  data/  │  │   logs/   │  │
│  │ (GGUF)  │  │  (DOCX)  │  │ (Excel) │  │  (JSON)   │  │
│  └─────────┘  └──────────┘  └─────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 5.2 Технологический стек

| Слой | Технология |
|------|------------|
| Frontend | Streamlit |
| Backend | Python 3.11 |
| LLM | llama-cpp-python + GGUF модель |
| RAG | sentence-transformers + ChromaDB |
| Email | imaplib (IMAP) |
| Documents | docx2txt, PyPDF2 |
| Excel | openpyxl, pandas |
| Security | cryptography (Fernet) |
| Container | Docker |
| Reverse Proxy | Nginx |
| SSL | Let's Encrypt |

---

## 🧪 6. Test Plan

### 6.1 Unit Tests

| Модуль | Тесты | Coverage Target |
|--------|-------|-----------------|
| utils/security.py | test_security.py | 90% |
| utils/auth.py | test_auth.py | 85% |
| utils/retry.py | test_retry.py | 85% |
| agents/email_agent.py | test_email.py | 70% |
| processors/document.py | test_document.py | 70% |

### 6.2 Integration Tests

| Сценарий | Описание |
|----------|----------|
| Email → Excel | Полный цикл обработки |
| Auth flow | Регистрация → Логин → Logout |
| LLM inference | Запрос → Ответ → Парсинг |

### 6.3 E2E Tests

| Сценарий | Шаги |
|----------|------|
| Happy path | Логин → Подключение к почте → Обработка → Скачивание Excel |
| Error handling | Неверный пароль, нет писем, ошибка LLM |

### 6.4 Security Tests

| Тест | Описание |
|------|----------|
| XSS prevention | Попытка инъекции в email subject |
| Path traversal | Попытка доступа к системным файлам |
| Brute force | Rate limiting после 5 попыток |
| Auth bypass | Доступ без авторизации |

---

## 📊 7. API Specification

### 7.1 Internal API (будущее)

```yaml
# Пока API нет - используется Streamlit UI
# При переходе на FastAPI:

POST /api/v1/auth/login
  Request: { username, password }
  Response: { token, expires_at }

POST /api/v1/email/connect
  Request: { email, password }
  Response: { connected: bool, message }

POST /api/v1/email/process
  Request: { scan_all: bool }
  Response: { contracts: [...], count }

GET /api/v1/export/excel
  Response: Excel file (binary)

GET /api/v1/metrics
  Response: { emails_processed, contracts_found, ... }
```

---

## 📅 8. Roadmap

### Phase 1: MVP (Текущий)
- ✅ Email agent (IMAP)
- ✅ Document processing (DOCX, PDF)
- ✅ LLM integration (local)
- ✅ Streamlit UI
- ✅ Excel export
- ✅ Basic auth
- ✅ Docker deployment

### Phase 2: Production-Ready
- ✅ Retry logic
- ✅ Metrics & logging
- ✅ CI/CD pipeline
- ✅ Security hardening
- 🔄 Unit tests (80% coverage)
- 🔄 Load testing

### Phase 3: Enhanced Features
- ⬜ FastAPI backend
- ⬜ OCR for scanned docs
- ⬜ Manual correction UI
- ⬜ Telegram notifications
- ⬜ Multi-user support

### Phase 4: Enterprise
- ⬜ CRM integration
- ⬜ Role-based access
- ⬜ Audit logging
- ⬜ Multi-language support

---

## 📎 9. Appendix

### 9.1 Глоссарий

| Термин | Определение |
|--------|-------------|
| LLM | Large Language Model - большая языковая модель |
| RAG | Retrieval-Augmented Generation - генерация с использованием поиска |
| GGUF | GPT-Generated Unified Format - формат квантизированных моделей |
| IMAP | Internet Message Access Protocol - протокол доступа к почте |
| Fernet | Симметричное шифрование из библиотеки cryptography |

### 9.2 Ссылки

- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [ChromaDB](https://www.trychroma.com/)
- [Let's Encrypt](https://letsencrypt.org/)

### 9.3 Контакты

- **Разработчик:** [Ваше имя]
- **Email:** [Ваш email]
- **Repository:** [GitHub URL]

---

*Документ обновлён: Январь 2026*
