import pandas as pd
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class ContractManager:
    """Менеджер для создания отдельных Excel файлов под каждый договор"""
    
    def __init__(self, output_dir: str = "contracts"):
        """
        Args:
            output_dir: Директория для сохранения Excel файлов договоров
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Счётчик для генерации номеров
        self.counter_file = self.output_dir / ".counter.txt"
        self.current_number = self._load_counter()
    
    def _load_counter(self) -> int:
        """Загрузка текущего номера из файла"""
        if self.counter_file.exists():
            try:
                with open(self.counter_file, 'r') as f:
                    return int(f.read().strip())
            except:
                return 0
        return 0
    
    def _save_counter(self):
        """Сохранение текущего номера"""
        with open(self.counter_file, 'w') as f:
            f.write(str(self.current_number))
    
    def _generate_registration_number(self) -> str:
        """Генерация уникального регистрационного номера"""
        self.current_number += 1
        self._save_counter()
        
        year = datetime.now().year
        return f"REG-{year}-{self.current_number:06d}"
    
    def is_contract(self, document_type: str, email_subject: str, email_body: str) -> bool:
        """
        Проверка, является ли документ договором
        
        Args:
            document_type: Тип документа из LLM
            email_subject: Тема письма
            email_body: Тело письма
        
        Returns:
            True если это договор, иначе False
        """
        # Ключевые слова для договоров
        contract_keywords = [
            'договор', 'контракт', 'соглашение', 'допсоглашение',
            'contract', 'agreement'
        ]
        
        # Проверяем тип документа
        doc_type_lower = document_type.lower()
        if any(keyword in doc_type_lower for keyword in contract_keywords):
            return True
        
        # Проверяем тему письма
        subject_lower = email_subject.lower()
        if any(keyword in subject_lower for keyword in contract_keywords):
            return True
        
        # Проверяем тело письма (первые 500 символов)
        body_lower = email_body[:500].lower()
        if any(keyword in body_lower for keyword in contract_keywords):
            # Дополнительная проверка: есть ли признаки договора
            contract_indicators = ['номер', 'стороны', 'заключен', 'сумма', 'срок']
            if sum(1 for ind in contract_indicators if ind in body_lower) >= 2:
                return True
        
        return False
    
    def create_contract_file(self, contract_data: Dict) -> Optional[str]:
        """
        Создание отдельного Excel файла для договора
        
        Args:
            contract_data: Словарь с данными договора
        
        Returns:
            Регистрационный номер или None при ошибке
        """
        try:
            # Генерируем регистрационный номер
            reg_number = self._generate_registration_number()
            
            # Формируем имя файла
            # Вариант 1: По номеру регистрации
            filename = f"{reg_number}.xlsx"
            
            # Вариант 2: По названию договора (закомментировано)
            # safe_name = self._sanitize_filename(contract_data.get('description', 'договор'))
            # filename = f"{reg_number}_{safe_name}.xlsx"
            
            file_path = self.output_dir / filename
            
            # Создаём DataFrame с одной строкой
            df = pd.DataFrame([{
                '№': 1,  # Номер строки (всегда 1, т.к. один договор = один файл)
                'Регистрационный номер': reg_number,
                'Дата входящего': contract_data.get('incoming_date', datetime.now().strftime('%Y-%m-%d')),
                'Тема письма': contract_data.get('subject', ''),
                'Краткое описание': contract_data.get('brief_description', contract_data.get('description', '')),
                'Почта отправителя': contract_data.get('from', ''),
                'Тип документа': contract_data.get('document_type', ''),
                'Ответственный': contract_data.get('responsible_person', 'Не указано'),
                'Срок/Дата': contract_data.get('deadline', 'Не указан'),
                'Сумма': contract_data.get('amount', 'Не указана'),
                'Дата обработки': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Статус': 'Новый'
            }])
            
            # Сохраняем в Excel
            df.to_excel(file_path, index=False, sheet_name='Договор')
            
            logger.info(f"[OK] Создан файл договора: {filename}")
            logger.info(f"   Регистрационный номер: {reg_number}")
            logger.info(f"   Путь: {file_path}")
            
            return reg_number
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка создания файла договора: {e}")
            return None
    
    def _sanitize_filename(self, name: str, max_length: int = 50) -> str:
        """Очистка имени файла от недопустимых символов"""
        # Убираем недопустимые символы
        import re
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
        
        # Ограничиваем длину
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized.strip()
    
    def get_statistics(self) -> Dict:
        """Получение статистики по договорам"""
        excel_files = list(self.output_dir.glob("*.xlsx"))
        
        return {
            'total_contracts': len(excel_files),
            'current_number': self.current_number,
            'last_created': max(
                (f.stat().st_mtime for f in excel_files), 
                default=0
            )
        }
    
    def list_contracts(self, limit: int = 10) -> list:
        """Получение списка последних договоров"""
        excel_files = sorted(
            self.output_dir.glob("*.xlsx"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        
        contracts = []
        for file_path in excel_files[:limit]:
            try:
                df = pd.read_excel(file_path)
                if not df.empty:
                    contracts.append({
                        'file': file_path.name,
                        'reg_number': df.iloc[0]['Регистрационный номер'],
                        'description': df.iloc[0]['Краткое описание'],
                        'date': df.iloc[0]['Дата входящего']
                    })
            except Exception as e:
                logger.warning(f"Ошибка чтения {file_path.name}: {e}")
        
        return contracts


class SkippedEmailsLog:
    """Логирование пропущенных (не договорных) писем"""
    
    def __init__(self, log_file: str = "data/skipped_emails.xlsx"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log_skipped(self, email_data: Dict, reason: str = "Не договор"):
        """
        Логирование пропущенного письма
        
        Args:
            email_data: Данные письма
            reason: Причина пропуска
        """
        try:
            # Загружаем существующий лог или создаём новый
            if self.log_file.exists():
                df = pd.read_excel(self.log_file)
            else:
                df = pd.DataFrame(columns=[
                    'Дата лога', 'Тема', 'От кого', 'Дата письма', 
                    'Причина пропуска', 'Тип документа'
                ])
            
            # Добавляем новую запись
            new_row = pd.DataFrame([{
                'Дата лога': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Тема': email_data.get('subject', ''),
                'От кого': email_data.get('from', ''),
                'Дата письма': email_data.get('date', ''),
                'Причина пропуска': reason,
                'Тип документа': email_data.get('document_type', 'Не определено')
            }])
            
            df = pd.concat([df, new_row], ignore_index=True)
            
            # Сохраняем (оставляем только последние 1000 записей)
            df = df.tail(1000)
            df.to_excel(self.log_file, index=False)
            
            logger.debug(f"📝 Пропущено письмо: {email_data.get('subject', '')[:50]}")
            
        except Exception as e:
            logger.warning(f"Ошибка логирования пропущенного письма: {e}")