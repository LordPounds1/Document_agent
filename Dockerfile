# Document Processing Agent - Dockerfile
# Streamlit + llama-cpp-python (CPU версия) + Playwright для WhatsApp

FROM python:3.11-slim

# Метаданные
LABEL maintainer="Document Agent Team"
LABEL description="AI-агент для обработки юридических документов из почты"
LABEL version="1.1"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Playwright settings
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# Рабочая директория
WORKDIR /app

# Системные зависимости для llama-cpp-python и Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    build-essential \
    cmake \
    git \
    curl \
    # Playwright browser dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    # Fonts for WhatsApp Web
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Установка Playwright браузера (Chromium)
RUN playwright install chromium && \
    playwright install-deps chromium

# Копирование исходного кода
COPY . .

# Создание директорий
RUN mkdir -p /app/models /app/templates /app/data /app/logs

# Порт Streamlit
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Точка входа
ENTRYPOINT ["streamlit", "run", ".streamlit/app_streamlit.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
