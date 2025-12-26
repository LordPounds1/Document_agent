import logging
import json
import re
import os
import tempfile
from typing import Dict, Optional
from docx import Document
from pathlib import Path

# Попытка импорта библиотек для старых форматов
try:
    import textract
except ImportError:
    textract = None

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Обработчик документов с использованием LLM"""
    
    def __init__(self, model_path: Optional[str] = None):
        self.llm_client = None
        self.model_path = model_path
        
        if model_path:
            self._init_local_model(model_path)

    def _init_local_model(self, model_path: str):
        try:
            from llama_cpp import Llama
            logger.info(f"Загрузка локальной модели: {model_path}")
            
            # ИЗМЕНЕНИЕ 1: Увеличиваем контекст
            # n_ctx=0 использует значение из модели (обычно 32k для Mistral v0.3),
            # но для безопасности ставим явные 16384 (хватит на ~50 страниц текста)
            self.llm_client = Llama(
                model_path=model_path,
                n_ctx=16384,          # Было 4096 -> стало 16384
                n_gpu_layers=35,      # Если падает по памяти GPU, уменьши это число (напр. до 20)
                verbose=False
            )
            logger.info(f"[OK] Локальная модель успешно загружена (Context: 16k)")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            self.llm_client = None

    def extract_text_from_attachments(self, attachments: list) -> str:
        """Извлечение текста из вложений через временные файлы (поддержка .doc, .docx, .pdf)"""
        texts = []

        for att in attachments or []:
            filename = att.get("filename", "")
            file_data = att.get("data")
            
            if not filename or not file_data:
                continue

            suffix = Path(filename).suffix.lower()
            if suffix not in ['.doc', '.docx', '.pdf']:
                continue

            try:
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    tmp_file.write(file_data)
                    tmp_path = tmp_file.name
                
                logger.info(f"Обработка файла: {filename}")
                extracted_text = ""

                # .DOCX
                if suffix == ".docx":
                    try:
                        doc = Document(tmp_path)
                        extracted_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                    except Exception as e:
                        logger.error(f"Ошибка чтения .docx {filename}: {e}")

                # .DOC
                elif suffix == ".doc":
                    if textract:
                        try:
                            extracted_text = textract.process(tmp_path).decode('utf-8')
                        except: pass
                    
                    if not extracted_text:
                        # Бинарный фоллбэк
                        with open(tmp_path, 'rb') as f:
                            binary = f.read()
                            # Фильтр: оставляем кириллицу (C0-FF) и ASCII
                            text = ''.join(chr(b) if (0xC0 <= b <= 0xFF) or (32 <= b < 127) or b in [10, 13] else ' ' for b in binary)
                            extracted_text = re.sub(r'\s+', ' ', text).strip()

                # .PDF
                elif suffix == ".pdf":
                    try:
                        import PyPDF2
                        with open(tmp_path, 'rb') as pdf_file:
                            reader = PyPDF2.PdfReader(pdf_file)
                            extracted_text = ""
                            for page_num in range(len(reader.pages)):
                                page = reader.pages[page_num]
                                extracted_text += page.extract_text() + "\n"
                            extracted_text = extracted_text.strip()
                    except Exception as e:
                        logger.debug(f"PyPDF2 не помог с {filename}: {e}")
                        try:
                            import pdfplumber
                            with pdfplumber.open(tmp_path) as pdf:
                                extracted_text = ""
                                for page in pdf.pages:
                                    extracted_text += page.extract_text() or ""
                                    extracted_text += "\n"
                            extracted_text = extracted_text.strip()
                        except Exception as e2:
                            logger.error(f"Ошибка чтения PDF {filename}: {e2}")

                if extracted_text and len(extracted_text) > 50:
                    texts.append(f"--- ДОКУМЕНТ: {filename} ---\n{extracted_text}")
                else:
                    logger.warning(f"⚠️ Не удалось извлечь текст из {filename}")

            except Exception as e:
                logger.error(f"Ошибка {filename}: {e}")
            finally:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except: pass

        return "\n\n".join(texts)

    def extract_info(self, email_text: str, email_subject: str, attachments: list = None) -> Dict:
        """Подготовка текста для LLM"""
        
        contract_text = self.extract_text_from_attachments(attachments)

        if contract_text.strip():
            logger.info("📄 Подготовка текста для LLM...")
            
            # ИЗМЕНЕНИЕ 2: Умная обрезка (Head + Tail)
            # Берем первые 7000 символов (Преамбула, Предмет) и последние 3000 (Реквизиты, Подписи)
            if len(contract_text) > 12000:
                full_text = contract_text[:8000] + "\n\n...[ПРОПУСК СТАНДАРТНЫХ УСЛОВИЙ]...\n\n" + contract_text[-4000:]
                logger.info(f"✂️ Текст сокращен: {len(contract_text)} -> {len(full_text)} символов")
            else:
                full_text = contract_text
        else:
            logger.warning("[WARN] Текст вложений пуст! Использую тело письма.")
            # Если тело письма достаточно длинное (например, мы подставили шаблон),
            # передаём в LLM только его — чтобы тема/заголовок письма не задавали ответ.
            if email_text and len(email_text) > 500:
                full_text = email_text
            else:
                full_text = f"ТЕМА: {email_subject}\nТЕКСТ ПИСЬМА:\n{email_text}"

        if self.llm_client:
            return self._extract_with_llm(full_text, email_subject)
        else:
            return self._extract_simple(full_text, email_subject)

    def _extract_with_llm(self, text_input: str, email_subject: str) -> Dict:
        """Запрос к LLM с исправленным форматом вывода"""
        # Улучшённый промпт: просим краткое резюме (3-5 предложений) и явно возвращаем поле
        # `brief_description`, чтобы затем его сохранить в Excel.
        prompt = f"""
system
Ты — помощник юриста. Твоя задача: прочитать ТОЛЬКО текст договора (без названий файлов и без темы письма)
и дать развёрнутый вывод о сути договора в 3-5 предложениях (300-600 символов).
Захвати ключевые детали: стороны, предмет, сумму, сроки, основные условия.
Пиши ТОЛЬКО на русском языке.

Требуемый JSON-формат (строго):
{{
  "document_type": "(Договор|Акт|Доп.соглашение|Другое)",
  "brief_description": "(Развёрнутое резюме 3-5 предложений, не более 600 символов, ключевые детали)",
  "summary": "(Более подробное описание, при необходимости)",
  "responsible_person": "(ФИО или организация)",
  "deadline": "(дата или срок)",
  "amount": "(сумма и валюта)"
}}

user
Вот текст для анализа:
<<<
{text_input}
>>>
"""

        try:
            response = self.llm_client(
                prompt,
                max_tokens=800,
                temperature=0.01,
                top_p=0.9,
                echo=False
            )

            # Поддерживаем разные форматы ответа от llama_cpp/обёрток
            if isinstance(response, dict) and 'choices' in response:
                result_text = response['choices'][0].get('text', '').strip()
            else:
                result_text = str(response).strip()

            logger.info(f"[DEBUG] Raw LLM output (первые 500 симв): {result_text[:500]}")
            
            # Если результат слишком короткий - это подозрительно
            if len(result_text) < 50:
                logger.warning(f"[WARN] LLM output очень короткий ({len(result_text)} симв): {result_text}")

            # Попытка вытащить JSON из вывода модели
            start = result_text.find('{')
            end = result_text.rfind('}')
            if start != -1 and end != -1 and end > start:
                full_json_str = result_text[start:end+1]
            else:
                # Если модель вернула только тело без фигурных скобок, пытаемся подставить
                full_json_str = result_text
                if not full_json_str.strip().startswith('{'):
                    full_json_str = '{' + full_json_str
                if not full_json_str.strip().endswith('}'):
                    full_json_str = full_json_str + '}'

            full_json_str = full_json_str.replace('```json', '').replace('```', '').strip()

            # Попытка распарсить JSON; при ошибке — робустный фоллбэк
            try:
                data = json.loads(full_json_str)
            except Exception as e:
                logger.warning(f"JSON parse failed: {e}. Попытка вытянуть значения из вывода модели.")
                
                data = {}
                
                # Достаём значения из raw LLM output используя regex для каждого поля
                fields_to_extract = {
                    'brief_description': [r'brief_description["\']?\s*[:=]\s*["\']?([^"\']*)["\']?(?:,|$)', 
                                         r'Кратк(?:ое)?.*?описа[ни]*е\s*[:\-]\s*([^,\n]*)'],
                    'responsible_person': [r'responsible_person["\']?\s*[:=]\s*["\']?([^"\']*)["\']?(?:,|$)',
                                          r'Отвественн(?:ый|ые)?\s*[:\-]\s*([^,\n]*)'],
                    'deadline': [r'deadline["\']?\s*[:=]\s*["\']?([^"\']*)["\']?(?:,|$)',
                                r'Срок\s*[:\-]\s*([^,\n]*)'],
                    'amount': [r'amount["\']?\s*[:=]\s*["\']?([^"\']*)["\']?(?:,|$)',
                              r'Сумма\s*[:\-]\s*([^,\n]*)'],
                    'document_type': [r'document_type["\']?\s*[:=]\s*["\']?([^",\n}]*)', 
                                     r'Тип документа\s*[:\-]\s*([^,\n]*)']
                }
                
                for field, patterns in fields_to_extract.items():
                    for pattern in patterns:
                        m = re.search(pattern, result_text, re.IGNORECASE | re.DOTALL)
                        if m:
                            val = m.group(1).strip()
                            # Очищаем от кавычек и запятых в конце
                            val = re.sub(r'["\',}\n]*$', '', val).strip()
                            if val and val.lower() not in ['none', 'null', 'string']:
                                data[field] = val
                                break
                
                # FALLBACK: Если brief_description всё ещё не найден, берём первые предложения
                if 'brief_description' not in data or not data.get('brief_description'):
                    # Убираем служебные линии
                    cleaned = re.sub(r'[-]{3,}.*?[-]{3,}', '', result_text, flags=re.IGNORECASE)
                    cleaned = re.sub(r'(ТЕМА|user|system|assistant|JSON)[\s:]*', '', cleaned, flags=re.IGNORECASE)
                    # Берём первые 3-5 предложений
                    sentences = [s.strip() for s in re.split(r'[.!?]+', cleaned) if s.strip() and len(s.strip()) > 15]
                    if sentences:
                        brief = '. '.join(sentences[:5]).strip() + '.'
                        if len(brief) > 50:
                            data['brief_description'] = brief

            def clean_val(key, default=''):
                val = str(data.get(key, default) or '').strip()
                if val.lower() in ['string', '...', 'null', '', 'none', 'тип']:
                    return default
                return val

            # Если brief_description пустой, используем summary или часть исходного текста
            brief = clean_val('brief_description', '')
            if not brief:
                brief = clean_val('summary', '')
            if not brief:
                cleaned_text2 = re.sub(r"---[^\n]*---\s*", "", text_input, flags=re.IGNORECASE)
                brief = cleaned_text2.strip()[:400]

            return {
                'document_type': self._normalize_doc_type(clean_val('document_type', 'Договор')),
                'brief_description': brief[:1200],
                'description': clean_val('summary', '')[:2000],
                'responsible_person': clean_val('responsible_person', 'Не указано'),
                'deadline': clean_val('deadline', 'Не указан'),
                'amount': clean_val('amount', 'Не указана')
            }

        except Exception as e:
            logger.error(f"Ошибка LLM или парсинга: {e}")
            return self._extract_simple(text_input, email_subject)

    # --- Простые методы без изменений ---
    def _extract_simple(self, text: str, subject: str) -> Dict:
        return {
            'document_type': self._detect_document_type(text),
            'description': subject,
            'responsible_person': 'Не удалось извлечь',
            'deadline': self._find_date(text),
            'amount': self._find_amount(text)
        }
        
    def _detect_document_type(self, text: str) -> str:
        text = text.lower()
        if 'договор' in text: return 'Договор'
        if 'акт' in text: return 'Акт'
        return 'Документ'

    def _find_date(self, text: str) -> str:
        match = re.search(r'\d{2}[./]\d{2}[./]\d{4}', text)
        return match.group(0) if match else 'Не указан'

    def _find_amount(self, text: str) -> str:
        match = re.search(r'(\d[\d\s,]*)\s*(руб|тенге)', text)
        return match.group(0) if match else 'Не указана'

    def _normalize_doc_type(self, val): return str(val).strip()
    def _clean_person_name(self, val): return str(val).strip()
    def _normalize_date(self, val): return str(val).strip()
    def _normalize_amount(self, val): return str(val).strip()