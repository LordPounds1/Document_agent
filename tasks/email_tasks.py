"""Email monitoring background tasks.

Эти задачи запускаются Celery worker в фоне,
независимо от того, открыт ли браузер пользователя.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from celery import shared_task

from utils.storage import MonitorStorage, MonitorConfig, ProcessedDocument

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_email_task(
    self,
    email_address: str,
    password: str,
    scan_all: bool = False
) -> Dict[str, Any]:
    """Проверка почты на наличие новых договоров.
    
    Args:
        email_address: Email адрес
        password: Пароль (app password)
        scan_all: Проверять все письма или только новые
        
    Returns:
        Результат проверки с найденными договорами
    """
    from agents.email_agent import EmailAgent
    from processors.document import DocumentProcessor
    from core.rag import SimpleRAG
    from config import Config
    
    logger.info(f"[Background] Checking email: {email_address}")
    
    storage = MonitorStorage()
    result = {
        'success': False,
        'email': email_address,
        'checked_at': datetime.now().isoformat(),
        'contracts_found': 0,
        'contracts': [],
        'error': None
    }
    
    try:
        # Инициализация агентов
        email_agent = EmailAgent()
        
        # Подключение к почте
        if not email_agent.connect(email_address, password):
            result['error'] = 'Failed to connect to email'
            logger.error(f"[Background] Failed to connect: {email_address}")
            return result
        
        # Инициализация процессора
        model_path = Config.get_model_path()
        processor = None
        rag = None
        
        if model_path:
            processor = DocumentProcessor(
                model_path=model_path,
                templates_dir="templates"
            )
        
        rag = SimpleRAG(templates_dir="templates")
        
        # Получаем уже обработанные email_id
        processed_ids = storage.get_processed_email_ids(email_address)
        
        # Получаем письма
        emails = email_agent.fetch_emails(
            unread_only=not scan_all,
            limit=50
        )
        
        logger.info(f"[Background] Found {len(emails)} emails to check")
        
        found_contracts = []
        
        for email_data in emails:
            email_id = email_data.get('id', '')
            
            # Пропускаем уже обработанные
            if email_id in processed_ids:
                continue
            
            contract_text = None
            source = None
            
            # Проверяем тело письма
            body = email_data.get('body', '')
            if body and rag:
                is_contract, confidence = rag.is_contract(body)
                if is_contract:
                    contract_text = body
                    source = 'email_body'
            
            # Проверяем вложения
            if not contract_text:
                for attachment in email_data.get('attachments', []):
                    filename = attachment.get('filename', '').lower()
                    
                    if filename.endswith(('.docx', '.pdf', '.txt', '.doc')):
                        text = email_agent.get_attachment_text(attachment)
                        
                        if text and rag:
                            is_contract, confidence = rag.is_contract(text)
                            if is_contract:
                                contract_text = text
                                source = f'attachment:{attachment.get("filename")}'
                                break
            
            # Если нашли договор - обрабатываем
            if contract_text:
                # Обработка с LLM
                if processor:
                    contract_info = processor.extract_contract_info(contract_text)
                else:
                    contract_info = {
                        'document_type': 'Договор',
                        'summary': contract_text[:150] + '...',
                        'parties': '',
                        'amount': '',
                        'responsible': ''
                    }
                
                # Получаем дату
                email_date = email_data.get('date', datetime.now())
                if hasattr(email_date, 'tzinfo') and email_date.tzinfo:
                    email_date = email_date.replace(tzinfo=None)
                
                # Сохраняем результат
                doc = ProcessedDocument(
                    email_id=email_id,
                    email_address=email_address,
                    email_from=email_data.get('from', ''),
                    email_subject=email_data.get('subject', ''),
                    email_date=email_date,
                    document_type=contract_info.get('document_type', 'Договор'),
                    summary=contract_info.get('summary', ''),
                    parties=contract_info.get('parties', ''),
                    amount=contract_info.get('amount', ''),
                    responsible=contract_info.get('responsible', ''),
                    source=source or 'unknown',
                    processed_at=datetime.now()
                )
                
                storage.save_document(doc)
                found_contracts.append(doc.to_dict())
                
                logger.info(f"[Background] Found contract: {email_data.get('subject', '')[:50]}")
        
        # Отключаемся от почты
        email_agent.disconnect()
        
        # Обновляем время последней проверки
        storage.update_last_check(email_address)
        
        result['success'] = True
        result['contracts_found'] = len(found_contracts)
        result['contracts'] = found_contracts
        
        logger.info(f"[Background] Completed. Found {len(found_contracts)} contracts")
        
    except Exception as e:
        logger.error(f"[Background] Error checking email: {e}")
        result['error'] = str(e)
        
        # Retry на ошибках сети
        if 'connection' in str(e).lower() or 'timeout' in str(e).lower():
            raise self.retry(exc=e)
    
    return result


@shared_task
def check_all_monitored_emails() -> Dict[str, Any]:
    """Проверка всех email адресов с активным мониторингом.
    
    Эта задача вызывается периодически через Celery Beat.
    """
    from utils.storage import MonitorStorage
    
    logger.info("[Background] Starting scheduled email check for all monitors")
    
    storage = MonitorStorage()
    configs = storage.get_all_active_configs()
    
    results = {
        'checked_at': datetime.now().isoformat(),
        'total_configs': len(configs),
        'successful': 0,
        'failed': 0,
        'total_contracts': 0,
        'details': []
    }
    
    for config in configs:
        try:
            # Запускаем проверку для каждого email
            task_result = check_email_task.delay(
                email_address=config.email_address,
                password=config.password,
                scan_all=config.scan_all
            )
            
            results['details'].append({
                'email': config.email_address,
                'task_id': task_result.id,
                'status': 'queued'
            })
            
        except Exception as e:
            logger.error(f"[Background] Failed to queue task for {config.email_address}: {e}")
            results['failed'] += 1
            results['details'].append({
                'email': config.email_address,
                'error': str(e),
                'status': 'failed'
            })
    
    logger.info(f"[Background] Queued {len(configs)} email checks")
    
    return results


@shared_task
def cleanup_old_results(days: int = 30) -> Dict[str, Any]:
    """Очистка старых результатов.
    
    Args:
        days: Удалять результаты старше N дней
    """
    from utils.storage import MonitorStorage
    
    logger.info(f"[Background] Cleaning up results older than {days} days")
    
    storage = MonitorStorage()
    deleted_count = storage.cleanup_old_documents(days)
    
    return {
        'cleaned_at': datetime.now().isoformat(),
        'deleted_count': deleted_count
    }


@shared_task(bind=True)
def start_email_monitoring(
    self,
    email_address: str,
    password: str,
    scan_all: bool = True,
    interval_minutes: int = 5
) -> Dict[str, Any]:
    """Запуск мониторинга для email адреса.
    
    Сохраняет конфигурацию в хранилище, после чего
    периодическая задача будет проверять этот email.
    """
    from utils.storage import MonitorStorage, MonitorConfig
    
    logger.info(f"[Background] Starting monitoring for: {email_address}")
    
    storage = MonitorStorage()
    
    # Сохраняем конфигурацию
    config = MonitorConfig(
        email_address=email_address,
        password=password,
        scan_all=scan_all,
        interval_minutes=interval_minutes,
        is_active=True,
        created_at=datetime.now()
    )
    
    storage.save_config(config)
    
    # Сразу запускаем первую проверку
    check_email_task.delay(email_address, password, scan_all)
    
    return {
        'success': True,
        'email': email_address,
        'message': 'Monitoring started'
    }


@shared_task
def stop_email_monitoring(email_address: str) -> Dict[str, Any]:
    """Остановка мониторинга для email адреса."""
    from utils.storage import MonitorStorage
    
    logger.info(f"[Background] Stopping monitoring for: {email_address}")
    
    storage = MonitorStorage()
    storage.deactivate_config(email_address)
    
    return {
        'success': True,
        'email': email_address,
        'message': 'Monitoring stopped'
    }
