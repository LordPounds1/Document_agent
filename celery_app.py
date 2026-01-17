"""Celery application for background tasks.

Запуск worker:
    celery -A celery_app worker --loglevel=info

Запуск beat (периодические задачи):
    celery -A celery_app beat --loglevel=info

Запуск flower (мониторинг):
    celery -A celery_app flower --port=5555
"""

import os

from celery import Celery
from celery.schedules import crontab
# Redis URL из переменных окружения
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Создаём Celery приложение
app = Celery(
    'document_agent',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks.email_tasks', 'tasks.whatsapp_tasks']
)

# Конфигурация Celery
app.conf.update(
    # Сериализация
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Таймзона
    timezone='UTC',
    enable_utc=True,

    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Результаты хранятся 24 часа
    result_expires=86400,

    # Ограничения
    task_soft_time_limit=300,  # 5 минут soft limit
    task_time_limit=600,  # 10 минут hard limit

    # Worker
    worker_prefetch_multiplier=1,
    worker_concurrency=2,  # 2 параллельных задачи (LLM ограничение)
)

# Периодические задачи (Celery Beat)
app.conf.beat_schedule = {
    # Проверка почты каждые 5 минут
    'check-email-every-5-minutes': {
        'task': 'tasks.email_tasks.check_all_monitored_emails',
        'schedule': crontab(minute='*/5'),
    },
    # Очистка старых результатов раз в день
    'cleanup-old-results-daily': {
        'task': 'tasks.email_tasks.cleanup_old_results',
        'schedule': crontab(hour=3, minute=0),
    },
}

if __name__ == '__main__':
    app.start()
