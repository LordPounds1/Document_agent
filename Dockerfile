# Document Processing Agent - Dockerfile
# Streamlit + llama-cpp-python (CPU версия)

FROM python:3.11-slim

# Метаданные
LABEL maintainer="Document Agent Team"
LABEL description="AI-агент для обработки юридических документов из почты"
LABEL version="1.0"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Системные зависимости для llama-cpp-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

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
