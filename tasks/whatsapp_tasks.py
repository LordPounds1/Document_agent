"""WhatsApp monitoring background tasks.

Placeholder для будущей реализации фонового мониторинга WhatsApp.
WhatsApp мониторинг сложнее из-за необходимости браузера.
"""

import logging
from datetime import datetime
from typing import Any
from celery import shared_task
logger = logging.getLogger(__name__)


@shared_task
def check_whatsapp_documents() -> dict[str, Any]:
    """Проверка WhatsApp на новые документы.

    Примечание: WhatsApp мониторинг требует headless browser,
    что сложнее реализовать в фоне. Пока это placeholder.
    """
    logger.info("[Background] WhatsApp background monitoring not yet implemented")

    return {
        'success': False,
        'message': 'WhatsApp background monitoring requires browser session',
        'checked_at': datetime.now().isoformat()
    }
