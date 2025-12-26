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
    """Главный агент обработки документов с поддержкой Advanced RAG"""
    
    def __init__(self, test_mode: bool = False, enable_rag: bool = False):
        # Настройка логирования
        setup_logger(Config.LOG_LEVEL)
        self.logger = logging.getLogger(__name__)
        self.test_mode = test_mode
        
        # Инициализация компонентов
        self.email_agent = EmailAgent()
        
        # Инициализация обработчика документов с RAG
        if Config.MODEL_PATH and Config.MODEL_PATH != "None":
            self.document_processor = DocumentProcessor(
                model_path=Config.MODEL_PATH,
                enable_rag=enable_rag
            )
            self.logger.info(f"Используется модель: {Config.MODEL_PATH}")
            
            if enable_rag and self.document_processor.rag_enabled:
                self.logger.info("✅ Advanced RAG включен")
                # Индексируем шаблоны при инициализации
                self._index_templates()
            else:
                self.logger.info("ℹ️ Advanced RAG отключен (базовый режим)")
        else:
            self.document_processor = DocumentProcessor(enable_rag=False)
            self.logger.warning("Модель не указана, используется простой парсер")
        
        self.excel_manager = ExcelManager()
        self.contract_manager = ContractManager()
        
        self.logger.info("Агент инициализирован")
        self.logger.info(f"Загружено шаблонов: {len(Config.TEMPLATES)}")
    
    def _index_templates(self):
        """Индексирование шаблонов для RAG"""
        try:
            self.logger.info("📚 Индексирование шаблонов для RAG...")
            
            # Получаем пути к файлам шаблонов
            templates_dir = Config.TEMPLATES_DIR
            
            if not templates_dir.exists():
                self.logger.warning(f"Папка шаблонов не найдена: {templates_dir}")
                return False
            
            template_files = list(templates_dir.glob("*"))
            
            if not template_files:
                self.logger.warning("Нет файлов шаблонов для индексирования")
                return False
            
            # Фильтруем по расширениям
            supported_ext = {'.docx', '.doc', '.pdf', '.txt'}
            template_files = [f for f in template_files if f.suffix.lower() in supported_ext]
            
            if template_files:
                success = self.document_processor.index_templates(
                    [str(f) for f in template_files]
                )
                
                if success:
                    self.logger.info(f"✅ Успешно индексировано {len(template_files)} шаблонов")
                    return True
                else:
                    self.logger.warning("❌ Ошибка индексирования шаблонов")
                    return False
            else:
                self.logger.warning("Нет поддерживаемых файлов шаблонов")
                return False
        
        except Exception as e:
            self.logger.error(f"❌ Ошибка при индексировании шаблонов: {e}")
            return False
    
    def process_test_email(self, use_rag: bool = None):
        """
        Обработка тестового письма
        
        Args:
            use_rag: Использовать ли RAG анализ (если None, используется по умолчанию)
        """
        # По умолчанию используем RAG если он доступен
        if use_rag is None:
            use_rag = self.document_processor.rag_enabled
        
        # Базовый тестовый email
        test_email = {
            'id': 'test_001',
            'subject': 'Тестовый договор',
            'from': 'test@example.com',
            'body': "Тестовое тело письма. Вложение: шаблон договора.",
            'attachments': [],
            'date': datetime.now().isoformat(),
            'raw': None
        }

        # Используем уже загруженные шаблоны из Config.TEMPLATES
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
                    self.logger.warning("⚠️ Загруженные шаблоны слишком маленькие")
        except Exception as e:
            self.logger.warning(f"⚠️ Ошибка загрузки шаблонов: {e}")
        
        self.logger.info(f"[TEST] Обработка тестового письма (RAG: {use_rag})...")
        
        try:
            # Извлечение информации
            if use_rag and self.document_processor.rag_enabled:
                self.logger.info("[RAG] Используется Advanced RAG анализ")
                doc_info = self.document_processor.extract_info_with_rag(
                    email_text=test_email['body'],
                    email_subject=test_email['subject'],
                    attachments=test_email.get('attachments')
                )
            else:
                self.logger.info("[BASIC] Используется базовый анализ")
                doc_info = self.document_processor.extract_info(
                    email_text=test_email['body'],
                    email_subject=test_email['subject'],
                    attachments=test_email.get('attachments')
                )
            
            self.logger.info("[RESULTS] Результаты анализа:")
            self.logger.info(f"  Тип документа: {doc_info.get('document_type', 'неизвестно')}")
            self.logger.info(f"  Описание: {doc_info.get('brief_description', 'не указано')[:100]}")
            self.logger.info(f"  Ответственный: {doc_info.get('responsible_person', 'Не указано')}")
            self.logger.info(f"  Срок: {doc_info.get('deadline', 'Не указан')}")
            self.logger.info(f"  Сумма: {doc_info.get('amount', 'Не указана')}")
            
            # Сохраняем договор
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
            self.logger.error(f"❌ Ошибка обработки тестового письма: {e}", exc_info=True)
            return False
    
    def check_emails(self, use_rag: bool = None):
        """Проверка новых писем"""
        if use_rag is None:
            use_rag = self.document_processor.rag_enabled
        
        self.logger.info(f"📭 Проверка новых писем (RAG: {use_rag})...")
        
        # Подключаемся к почте
        if not self.email_agent.connect():
            self.logger.error("❌ Не удалось подключиться к почте")
            self.logger.info("📝 Проверьте настройки в .env файле")
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
    
    parser = argparse.ArgumentParser(description='Агент обработки документов с Advanced RAG')
    parser.add_argument('--once', action='store_true', help='Однократный запуск')
    parser.add_argument('--stats', action='store_true', help='Показать статистику')
    parser.add_argument('--download-model', action='store_true', help='Скачать модель')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (без реальной почты)')
    parser.add_argument('--rag', action='store_true', help='Включить Advanced RAG анализ')
    parser.add_argument('--index-templates', action='store_true', help='Индексировать шаблоны для RAG')
    parser.add_argument('--list-templates', action='store_true', help='Показать загруженные шаблоны')
    
    args = parser.parse_args()
    
    if args.download_model:
        try:
            from models.download_model import download_saiga_model
            download_saiga_model()
        except ImportError as e:
            print(f"❌ Не удалось загрузить модуль для скачивания модели: {e}")
            print("📝 Убедитесь, что файл models/download_model.py существует")
        return
    
    if not any([args.download_model, args.index_templates, args.list_templates, args.stats]):
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
    
    agent = DocumentProcessingAgent(test_mode=args.test, enable_rag=args.rag)
    
    if args.index_templates:
        print("\n📚 Индексирование шаблонов...")
        success = agent._index_templates()
        if success:
            print("✅ Индексирование завершено успешно!")
        else:
            print("❌ Ошибка индексирования")
        return
    
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
        
        if agent.document_processor.rag_enabled:
            print("\n🤖 RAG Status:")
            print("  ✅ Advanced RAG включен")
            if agent.document_processor.vector_store:
                vs_stats = agent.document_processor.vector_store.get_stats()
                print(f"  Vector Store: {vs_stats.get('store_type')}")
                print(f"  Индекс размер: {vs_stats.get('index_size')}")
        return
    
    if args.once or args.test:
        agent.run_once()
    else:
        agent.run_continuously()

if __name__ == "__main__":
    main()