import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from config import Config

logger = logging.getLogger(__name__)

class ExcelManager:
    """Менеджер для работы с Excel файлом"""
    
    def __init__(self, file_path: str = None):
        self.file_path = file_path or Config.EXCEL_FILE_PATH
        self.sheet_name = Config.EXCEL_SHEET_NAME
        
        # Создаем файл если не существует
        self._initialize_file()
    
    def _initialize_file(self):
        """Инициализация Excel файла с заголовками"""
        if not Path(self.file_path).exists():
            df = pd.DataFrame(columns=[
                "Порядковый номер",
                "Дата входящего",
                "Тема письма",
                "Описание документа",
                "Почта отправителя",
                "Ответственные",
                "Дата обработки",
                "Тип документа",
                "Срок обработки",
                "Статус",
                "ID письма"
            ])
            self._save_dataframe(df)
            logger.info(f"Создан новый файл: {self.file_path}")
    
    def get_next_order_number(self) -> int:
        """Получение следующего порядкового номера"""
        try:
            df = self._load_dataframe()
            if df.empty:
                return 1
            return int(df["Порядковый номер"].max()) + 1
        except:
            return 1
    
    def _validate_and_clean_description(self, desc: str) -> str:
        """Валидация и очистка описания от мусора (bot bot bot и т.п.)"""
        if not desc:
            return ""
        
        desc = str(desc).strip()
        
        # Проверяем на явный мусор (повторяющиеся короткие слова)
        words = desc.split()
        if len(words) > 0:
            # Если более 80% слов одинаковые и коротких (< 4 символа), это мусор
            word_counts = {}
            for word in words:
                word_lower = word.lower().strip('.,!?;:')
                if len(word_lower) < 4:  # Коротких слов
                    word_counts[word_lower] = word_counts.get(word_lower, 0) + 1
            
            if word_counts and len(words) > 5:
                max_count = max(word_counts.values())
                if max_count / len(words) > 0.5:  # Если 50%+ повторяющихся слов
                    logger.warning(f"⚠️ Обнаружен мусор в описании: {desc[:100]}")
                    return ""  # Возвращаем пустоту вместо мусора
        
        # Проверяем минимальную длину (должно быть хотя бы 15 символов для нормального описания)
        if len(desc) < 15:
            return ""
        
        return desc[:1200]  # Ограничиваем максимум 1200 символов
    
    def add_document(self, document_info: Dict[str, Any]) -> int:
        """Добавление документа в таблицу"""
        
        order_number = self.get_next_order_number()
        
        # Валидация описания
        brief_desc = self._validate_and_clean_description(
            document_info.get("brief_description", document_info.get("description", ""))
        )
        
        new_row = {
            "Порядковый номер": order_number,
            "Дата входящего": document_info.get("incoming_date", 
                                               datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "Тема письма": document_info.get("subject", ""),
            # Валидированное описание
            "Описание документа": brief_desc,
            "Почта отправителя": document_info.get("from", ""),
            "Ответственные": document_info.get("responsible_person", "Не указано"),
            "Дата обработки": datetime.now().strftime("%Y-%m-%d"),
            "Тип документа": document_info.get("document_type", "другое"),
            "Срок обработки": document_info.get("deadline", "Не указан"),
            "Статус": "Обработано",
            "ID письма": document_info.get("email_id", "")
        }
        
        try:
            df = self._load_dataframe()
            new_df = pd.DataFrame([new_row])
            df = pd.concat([df, new_df], ignore_index=True)
            
            # Сохраняем с форматированием
            self._save_dataframe(df)
            
            logger.info(f"Добавлен документ №{order_number}: {new_row['Тема письма'][:50]}")
            return order_number
            
        except Exception as e:
            logger.error(f"Ошибка добавления документа: {e}")
            return -1
    
    def find_document(self, order_number: int) -> Optional[Dict]:
        """Поиск документа по номеру"""
        try:
            df = self._load_dataframe()
            result = df[df["Порядковый номер"] == order_number]
            if not result.empty:
                return result.iloc[0].to_dict()
        except Exception as e:
            logger.error(f"Ошибка поиска документа: {e}")
        return None
    
    def get_statistics(self) -> Dict:
        """Получение статистики по документам"""
        try:
            df = self._load_dataframe()
            
            if df.empty:
                return {
                    "total": 0,
                    "by_type": {},
                    "by_responsible": {},
                    "pending": 0
                }
            
            stats = {
                "total": len(df),
                "by_type": df["Тип документа"].value_counts().to_dict(),
                "by_responsible": df["Ответственные"].value_counts().to_dict(),
                "pending": len(df[df["Статус"] != "Обработано"]),
                "last_update": df["Дата обработки"].max() if "Дата обработки" in df.columns else None
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {"total": 0, "error": str(e)}
    
    def _load_dataframe(self) -> pd.DataFrame:
        """Загрузка DataFrame из файла"""
        try:
            if Path(self.file_path).exists():
                return pd.read_excel(self.file_path, sheet_name=self.sheet_name)
        except Exception as e:
            logger.error(f"Ошибка загрузки Excel: {e}")
        
        return pd.DataFrame()
    
    def _save_dataframe(self, df: pd.DataFrame):
        """Сохранение DataFrame в файл"""
        try:
            # Сохраняем с авто-шириной колонок
            with pd.ExcelWriter(self.file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name=self.sheet_name, index=False)
                
                # Авто-ширина колонок
                worksheet = writer.sheets[self.sheet_name]
                for column in df.columns:
                    column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
                    worksheet.column_dimensions[chr(65 + list(df.columns).index(column))].width = min(column_width, 50)
                    
        except Exception as e:
            logger.error(f"Ошибка сохранения Excel: {e}")
            # Fallback: простое сохранение
            df.to_excel(self.file_path, sheet_name=self.sheet_name, index=False)