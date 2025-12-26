import logging
import time
import argparse
import schedule
from datetime import datetime
from typing import Dict, Any
import sys
from config import Config
from agents.email_agent import EmailAgent
from agents.document_processor import DocumentProcessor
from agents.excel_manager import ExcelManager
from agents.contract_manager import ContractManager
from utils.logger import setup_logger

def check_email_config():
    """Проверка конфигурации почты"""
    if not Config.EMAIL_ADDRESS or not Config.EMAIL_PASSWORD:
        print("[!] Не настроена почта")
        print("[*] Установите EMAIL_ADDRESS и EMAIL_PASSWORD в файл .env")
        return False
    
    print(f"[MAIL] Используется почта: {Config.EMAIL_ADDRESS}")
    print(f"[MAIL] Сервер: {Config.IMAP_SERVER}:{Config.IMAP_PORT}")
    
    if hasattr(Config, 'ENABLE_REPLIES') and Config.ENABLE_REPLIES:
        print(f"[SEND] Отправка ответов: ВКЛЮЧЕНА ({Config.SMTP_SERVER})")
    else:
        print(f"[SEND] Отправка ответов: ВЫКЛЮЧЕНА")
    
    return True

class DocumentProcessingAgent:
    """Главный агент обработки документов"""
    
    def __init__(self, test_mode: bool = False):
        # Настройка логирования
        setup_logger(Config.LOG_LEVEL)
        self.logger = logging.getLogger(__name__)
        self.test_mode = test_mode
        
        # Инициализация компонентов
        self.email_agent = EmailAgent()
        
        # Проверяем модель
        if Config.MODEL_PATH and Config.MODEL_PATH != "None":
            self.document_processor = DocumentProcessor(Config.MODEL_PATH)
            self.logger.info(f"Используется модель: {Config.MODEL_PATH}")
        else:
            self.document_processor = DocumentProcessor()
            self.logger.warning("Модель не указана, используется простой парсер")
        
        self.excel_manager = ExcelManager()
        self.contract_manager = ContractManager()
        
        self.logger.info("Агент инициализирован")
        self.logger.info(f"Загружено шаблонов: {len(Config.TEMPLATES)}")
        
        for name, template in Config.TEMPLATES.items():
            self.logger.debug(f"Шаблон '{name}': {len(template['content'])} символов")
    
    def process_test_email(self):
        """Обработка тестового письма"""
        # Базовый тестовый email; заменим тело/тему реальным шаблоном, если он доступен
        test_email = {
            'id': 'test_001',
            'subject': 'Тестовый договор',
            'from': 'test@example.com',
            'body': "Тестовое тело письма. Вложение: шаблон договора.",
            'attachments': [],
            'date': datetime.now().isoformat(),
            'raw': None
        }

        # Используем уже загруженные шаблоны из Config.TEMPLATES (49 шаблонов)
        try:
            if hasattr(Config, 'TEMPLATES') and Config.TEMPLATES:
                # Ищем непустые шаблоны (контент >100 символов)
                candidates = [(name, tmpl) for name, tmpl in Config.TEMPLATES.items() 
                             if tmpl.get('content') and len(str(tmpl.get('content', '')).strip()) > 100]
                
                if candidates:
                    import random
                    name, tmpl = random.choice(candidates)
                    content = tmpl.get('content', '')
                    test_email['subject'] = f"Тест: Договор {name}"
                    test_email['body'] = str(content)[:20000]
                    test_email['attachments'] = []
                    self.logger.info(f"[TEMPLATE] Тест использует шаблон: {name}")
                else:
                    self.logger.warning("⚠️ Загруженные шаблоны слишком маленькие — использую стандартный тест")
        except Exception as e:
            self.logger.warning(f"⚠️ Ошибка загрузки шаблонов: {e}")
        
        self.logger.info("[TEST] Обработка тестового письма...")
        
        try:
            # Извлечение информации
            doc_info = self.document_processor.extract_info(
                email_text=test_email['body'],
                email_subject=test_email['subject']
            )
            
            self.logger.info("[RESULTS] Результаты анализа:")
            self.logger.info(f"  Тип документа: {doc_info.get('document_type', 'неизвестно')}")
            self.logger.info(f"  Описание: {doc_info.get('brief_description', 'не указано')[:100]}")
            self.logger.info(f"  Ответственный: {doc_info.get('responsible_person', 'Не указано')}")
            self.logger.info(f"  Срок: {doc_info.get('deadline', 'Не указан')}")
            self.logger.info(f"  Сумма: {doc_info.get('amount', 'Не указана')}")
            
            # Для тестов: ТОЛЬКО создаём отдельный файл договора в contracts/
            # НЕ добавляем в documents.xlsx (это для реальных писем из почты)
            reg_number = self.contract_manager.create_contract_file({
                **test_email,
                **doc_info,
                "incoming_date": test_email['date'],
                "processing_date": datetime.now().isoformat()
            })
            
            if reg_number:
                self.logger.info(f"[CONTRACT] Договор сохранен в contracts/: {reg_number}")
                return True
            else:
                self.logger.error("[ERROR] Ошибка создания файла договора")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки тестового письма: {e}")
            return False
    
    def check_emails(self):
        """Проверка новых писем"""
        self.logger.info("📭 Проверка новых писем...")
        
        # Подключаемся к почте
        if not self.email_agent.connect():
            self.logger.error("❌ Не удалось подключиться к почте")
            self.logger.info("📝 Проверьте настройки в .env файле")
            self.logger.info("📝 Запустите: python setup_email.py")
            return
        
        try:
            # Получение непрочитанных писем
            emails = self.email_agent.fetch_unread_emails()
            
            if not emails:
                self.logger.info("📭 Новых писем нет")
                return
            
            self.logger.info(f"📨 Найдено {len(emails)} новых писем")
            
            # Обработка каждого письма
            results = []
            for email_data in emails:
                result = self._process_single_email(email_data)
                results.append(result)
            
            # Статистика
            successful = sum(1 for r in results if r.get('success', False))
            self.logger.info(f"✅ Обработано успешно: {successful}/{len(results)}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки писем: {e}")
        finally:
            self.email_agent.disconnect()
    
    def _process_single_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка одного письма"""
        try:
            # Извлечение информации из письма
            doc_info = self.document_processor.extract_info(
                email_text=email_data['body'],
                email_subject=email_data['subject'],
                attachments=email_data.get('attachments', [])
            )
            
            # Добавление в Excel
            order_number = self.excel_manager.add_document({
                **email_data,
                **doc_info,
                "incoming_date": email_data.get('date', datetime.now().isoformat()),
                "processing_date": datetime.now().isoformat()
            })
            
            if order_number > 0:
                # Пометить как прочитанное
                self.email_agent.mark_as_read(email_data['id'])
                
                # Создаём отдельный файл договора в contracts/
                reg_number = self.contract_manager.create_contract_file({
                    **email_data,
                    **doc_info,
                    "incoming_date": email_data.get('date', datetime.now().isoformat()),
                    "processing_date": datetime.now().isoformat()
                })
                
                self.logger.info(f"✅ Обработано письмо #{order_number}: {email_data['subject'][:50]}...")
                if reg_number:
                    self.logger.info(f"[CONTRACT] Договор сохранен: {reg_number}")
                
                return {
                    "success": True,
                    "order_number": order_number,
                    "document_type": doc_info.get("document_type", "неизвестно"),
                    "registration_number": reg_number
                }
            else:
                self.logger.error(f"❌ Ошибка добавления в Excel: {email_data['subject']}")
                return {"success": False, "error": "Excel error"}
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки письма: {e}")
            return {"success": False, "error": str(e)}
    
    def run_once(self):
        """Однократный запуск обработки"""
        if self.test_mode:
            self.process_test_email()
        else:
            self.check_emails()
    
    def run_continuously(self):
        """Непрерывный запуск с периодической проверкой"""
        self.logger.info(f"🔄 Запуск агента с интервалом {Config.CHECK_INTERVAL_MINUTES} минут")
        
        # Запускаем сразу
        self.run_once()
        
        # Планируем периодические запуски
        schedule.every(Config.CHECK_INTERVAL_MINUTES).minutes.do(self.run_once)
        
        self.logger.info("🚀 Агент запущен. Нажмите Ctrl+C для остановки.")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("⏹️ Остановка агента...")
            self.logger.info("👋 Агент остановлен")

def main():
    """Точка входа"""
    
    parser = argparse.ArgumentParser(description='Агент обработки документов')
    parser.add_argument('--once', action='store_true', help='Однократный запуск')
    parser.add_argument('--stats', action='store_true', help='Показать статистику')
    parser.add_argument('--download-model', action='store_true', help='Скачать модель')
    parser.add_argument('--setup-email', action='store_true', help='Настроить почту')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (без реальной почты)')
    parser.add_argument('--list-templates', action='store_true', help='Показать загруженные шаблоны')
    
    args = parser.parse_args()
    
    if args.setup_email:
        try:
            from setup_email import setup_email
            setup_email()
        except ImportError:
            print("❌ Файл setup_email.py не найден")
            print("📝 Создайте файл setup_email.py для настройки почты")
        return
    
    if args.download_model:
        try:
            from models.download_model import download_saiga_model
            download_saiga_model()
        except ImportError as e:
            print(f"❌ Не удалось загрузить модуль для скачивания модели: {e}")
            print("📝 Убедитесь, что файл models/download_model.py существует")
        return
    
    if not any([args.download_model, args.setup_email, args.list_templates, args.stats]):
        if not check_email_config():
            sys.exit(1)
    
    if args.list_templates:
        print("\n📋 Загруженные шаблоны:")
        for name, template in Config.TEMPLATES.items():
            print(f"\n{name}:")
            print(f"  Файл: {template['file_path']}")
            print(f"  Размер: {template['metadata']['size']} байт")
            print(f"  Тип: {template['metadata']['extension']}")
            print(f"  Символов: {len(template['content'])}")
            print(f"  Предпросмотр: {template['content'][:100]}...")
        return
    
    agent = DocumentProcessingAgent(test_mode=args.test)
    
    if args.stats:
        stats = agent.excel_manager.get_statistics()
        print("\n📊 Статистика документов:")
        print(f"Всего документов: {stats.get('total', 0)}")
        print(f"В ожидании: {stats.get('pending', 0)}")
        print(f"Последнее обновление: {stats.get('last_update', 'Нет данных')}")
        
        if stats.get('by_type'):
            print("\n📋 По типам:")
            for doc_type, count in stats.get('by_type', {}).items():
                print(f"  {doc_type}: {count}")
        return
    
    if args.once or args.test:
        agent.run_once()
    else:
        agent.run_continuously()

if __name__ == "__main__":
    main()