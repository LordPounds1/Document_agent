import logging
import json
import re
import os
import tempfile
from typing import Dict, Optional, List, Tuple
from docx import Document
from pathlib import Path

# LangChain интеграция
try:
    from langchain.schema import Document as LangChainDocument
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

# RAG модули
try:
    from agents.docling_parser import DoclingParser
    from agents.rag_chunking import RAGChunkingPipeline
    from agents.pre_retrieval import PreRetrievalPipeline
    from agents.post_retrieval import PostRetrievalPipeline
    from agents.vector_store import RAGVectorStore
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

# Попытка импорта библиотек для старых форматов
try:
    import textract
except ImportError:
    textract = None

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    Обработчик документов с использованием LLM и Advanced RAG
    
    Поддерживает:
    - Direct LLM анализ (базовый режим)
    - Advanced RAG (при наличии документов в базе)
    """
    
    def __init__(self, model_path: Optional[str] = None, enable_rag: bool = False):
        self.llm_client = None
        self.model_path = model_path
        self.rag_enabled = False
        
        # RAG компоненты
        self.docling_parser = None
        self.chunking_pipeline = None
        self.pre_retrieval = None
        self.post_retrieval = None
        self.vector_store = None
        
        if model_path:
            self._init_local_model(model_path)
        
        if enable_rag and RAG_AVAILABLE:
            self._init_rag_components()

    def _init_local_model(self, model_path: str):
        try:
            from llama_cpp import Llama
            logger.info(f"Загрузка локальной модели: {model_path}")
            
            self.llm_client = Llama(
                model_path=model_path,
                n_ctx=16384,
                n_gpu_layers=35,
                verbose=False
            )
            logger.info(f"[OK] Локальная модель успешно загружена (Context: 16k)")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки модели: {e}")
            self.llm_client = None
    
    def _init_rag_components(self):
        """Инициализация RAG компонентов"""
        try:
            if not LANGCHAIN_AVAILABLE or not RAG_AVAILABLE:
                logger.warning("LangChain или RAG модули не доступны")
                return
            
            from sentence_transformers import SentenceTransformer
            
            logger.info("[RAG] Инициализация Advanced RAG компонентов...")
            
            # Docling парсер
            self.docling_parser = DoclingParser()
            logger.info("  ✓ Docling Parser")
            
            # Chunking
            self.chunking_pipeline = RAGChunkingPipeline(
                chunk_size=1024,
                chunk_overlap=256,
                strategy="semantic"
            )
            logger.info("  ✓ RAG Chunking Pipeline")
            
            # Pre-Retrieval
            self.pre_retrieval = PreRetrievalPipeline(llm_client=self.llm_client)
            logger.info("  ✓ Pre-Retrieval Pipeline")
            
            # Post-Retrieval
            self.post_retrieval = PostRetrievalPipeline(use_reranking=True)
            logger.info("  ✓ Post-Retrieval Pipeline")
            
            # Vector Store
            embeddings = SentenceTransformer('intfloat/multilingual-e5-base')
            self.vector_store = RAGVectorStore(
                embeddings=embeddings,
                store_type="faiss",
                store_path="data/vector_store"
            )
            
            # Пытаемся загрузить существующий индекс
            if not self.vector_store.load():
                logger.info("  ✓ Vector Store (новый индекс)")
            else:
                logger.info("  ✓ Vector Store (загружен из сохранения)")
            
            self.rag_enabled = True
            logger.info("✅ Advanced RAG успешно инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации RAG: {e}")
            self.rag_enabled = False
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
        # Улучшённый промпт: использует 585+ реальных контрактов как обучающие примеры
        prompt = f"""system
Ты — опытный юрист с опытом работы с 585+ реальными казахстанскими контрактами.

Твоя задача: анализировать договоры и извлекать ключевые детали.

ИНСТРУКЦИИ:
1. Прочитай ТОЛЬКО текст договора (без названий файлов, без темы письма)
2. Найди стороны договора (организации, ИП, ФИО)
3. Определи тип документа (Договор/Акт/Доп.соглашение/др.)
4. Дай развёрнутое резюме 3-5 предложений (300-600 символов) с ключевыми деталями
5. Найди сумму контракта (числа + валюта), сроки выполнения, ответственное лицо
6. Пиши ТОЛЬКО на русском языке

Анализируй как юрист: учитывай реальные казахстанские практики контрактации.

Требуемый JSON-формат (строго):
{{
  "document_type": "(Договор|Акт|Доп.соглашение|Приложение|Письмо|Другое)",
  "brief_description": "(Краткое резюме 3-5 предложений, ключевые детали, 300-600 символов)",
  "summary": "(Более подробное описание)",
  "responsible_person": "(ФИО или организация, если известны)",
  "deadline": "(дата или срок выполнения, если указаны)",
  "amount": "(сумма и валюта, если указаны)"
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
    
    # ======================== RAG МЕТОДЫ ========================
    
    def index_templates(self, template_files: List[str]) -> bool:
        """
        Индексирование шаблонов документов в Vector Store для RAG
        
        Args:
            template_files: Список путей к файлам шаблонов
        
        Returns:
            True если успешно, False иначе
        """
        if not self.rag_enabled:
            logger.warning("RAG не включен, индексирование невозможно")
            return False
        
        try:
            logger.info(f"📚 Индексирование {len(template_files)} шаблонов...")
            all_documents = []
            
            for template_file in template_files:
                if not Path(template_file).exists():
                    logger.warning(f"Файл не найден: {template_file}")
                    continue
                
                # Парсируем документ
                docs = self.docling_parser.documents_to_langchain(
                    template_file,
                    source_name=Path(template_file).stem
                )
                
                all_documents.extend(docs)
            
            if not all_documents:
                logger.warning("Нет документов для индексирования")
                return False
            
            # Чанкируем
            logger.info(f"  Чанкирование {len(all_documents)} документов...")
            chunks = self.chunking_pipeline.process_pipeline(
                all_documents,
                merge_small=True,
                add_context=True
            )
            
            # Добавляем в Vector Store
            logger.info(f"  Добавление {len(chunks)} чанков в Vector Store...")
            success = self.vector_store.add_documents(chunks, batch_size=32)
            
            if success:
                logger.info(f"✅ Индексирование завершено: {len(chunks)} чанков")
                return True
            else:
                logger.error("❌ Ошибка добавления в Vector Store")
                return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка индексирования: {e}")
            return False
    
    def extract_info_with_rag(self, email_text: str, email_subject: str, 
                             attachments: list = None) -> Dict:
        """
        Извлечение информации с использованием RAG для лучшего анализа
        
        Использует похожие контракты из базы 585+ документов как примеры для LLM
        Стратегия: найти 3-5 наиболее похожих контрактов, использовать как контекст
        
        Args:
            email_text: Текст письма
            email_subject: Тема письма
            attachments: Вложения письма
        
        Returns:
            Словарь с информацией о документе
        """
        if not self.rag_enabled:
            logger.warning("RAG не включен, используется базовый анализ")
            return self.extract_info(email_text, email_subject, attachments)
        
        try:
            logger.info("[RAG] Анализ с использованием контекста из 585+ контрактов...")
            
            # Шаг 1: Извлекаем текст документа
            contract_text = self.extract_text_from_attachments(attachments)
            
            if not contract_text.strip():
                contract_text = email_text
            
            # Обрезаем для LLM (Head + Tail метод)
            if len(contract_text) > 12000:
                full_text = contract_text[:8000] + "\n\n[...текст сокращен для краткости...]\n\n" + contract_text[-4000:]
            else:
                full_text = contract_text
            
            # Шаг 2: Pre-Retrieval обработка запроса (расширение запроса)
            query = f"Тип документа: {email_subject}. Текст: {contract_text[:500]}"
            processed_query = self.pre_retrieval.process_query(
                query,
                method="expansion"
            )
            
            logger.info(f"  Pre-Retrieval: создано {len(processed_query['variants'])} вариантов запроса")
            
            # Шаг 3: Поиск похожих контрактов в базе (найти 5 лучших примеров)
            search_queries = self.pre_retrieval.get_search_queries(processed_query)
            search_results = self.vector_store.search_multiple(search_queries, top_k=5)
            
            # Объединяем результаты поиска
            all_results = []
            for results in search_results.values():
                all_results.extend([doc for doc, _ in results])
            
            logger.info(f"  Поиск: найдено {len(all_results)} похожих контрактов из базы")
            
            # Шаг 4: Post-Retrieval обработка (переранжирование, суммирование)
            if all_results:
                final_docs = self.post_retrieval.process(
                    all_results,
                    query=query,
                    top_k=3,  # Берем топ-3 лучшие примеры
                    strategies=["rerank", "summary"]
                )
                
                # Форматируем контекст из найденных контрактов
                context_parts = []
                for i, doc in enumerate(final_docs[:3], 1):
                    context_parts.append(f"\n[ПРИМЕР КОНТРАКТА {i}]\n{doc[:500]}...")
                
                context = "\n".join(context_parts)
            else:
                context = ""
            
            logger.info(f"  Post-Retrieval: подготовлен контекст ({len(context)} символов)")
            
            # Шаг 5: LLM анализ с контекстом примеров из 585 контрактов
            if context:
                enhanced_prompt = f"""system
Ты — опытный юрист с опытом анализа 585+ казахстанских контрактов.

Используй следующие ПРИМЕРЫ ПОХОЖИХ КОНТРАКТОВ для лучшего понимания стиля и структуры:
{context}

Теперь проанализируй следующий новый контракт. Используй знания из примеров для более точного анализа.

user
АНАЛИЗИРУЕМЫЙ КОНТРАКТ:
{full_text}

Требуемый JSON-формат:
{{
  "document_type": "(Договор|Акт|Доп.соглашение|Приложение|Письмо|Другое)",
  "brief_description": "(Краткое резюме 3-5 предложений с ключевыми деталями, 300-600 символов)",
  "summary": "(Подробное описание)",
  "responsible_person": "(ФИО или организация)",
  "deadline": "(дата или срок)",
  "amount": "(сумма и валюта)"
}}

Ответь ТОЛЬКО JSON, без доп. текста."""
            else:
                enhanced_prompt = f"""system
Ты — опытный юрист с опытом анализа 585+ казахстанских контрактов.

Проанализируй следующий контракт как профессиональный юрист.

user
АНАЛИЗИРУЕМЫЙ КОНТРАКТ:
{full_text}

Требуемый JSON-формат:
{{
  "document_type": "(Договор|Акт|Доп.соглашение|Приложение|Письмо|Другое)",
  "brief_description": "(Краткое резюме 3-5 предложений, 300-600 символов)",
  "summary": "(Подробное описание)",
  "responsible_person": "(ФИО или организация)",
  "deadline": "(дата или срок)",
  "amount": "(сумма и валюта)"
}}

Ответь ТОЛЬКО JSON."""
            
            # Отправляем в LLM
            if self.llm_client:
                response = self.llm_client(
                    enhanced_prompt,
                    max_tokens=800,
                    temperature=0.01,
                    top_p=0.9,
                    echo=False
                )
                
                if isinstance(response, dict):
                    result_text = response['choices'][0].get('text', '').strip()
                else:
                    result_text = str(response).strip()
                
                logger.info(f"[RAG-LLM] Результат (первые 300 симв): {result_text[:300]}")
                
                # Парсим JSON результат
                return self._parse_llm_response(result_text, email_subject)
            else:
                logger.warning("LLM client не доступен, используется базовый анализ")
                return self._extract_simple(full_text, email_subject)
        
        except Exception as e:
            logger.error(f"❌ Ошибка RAG анализа: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self.extract_info(email_text, email_subject, attachments)
    
    def _get_extraction_prompt(self) -> str:
        """Получение промпта для извлечения информации"""
        return """Требуемый JSON-формат (строго):
{
  "document_type": "(Договор|Акт|Доп.соглашение|Другое)",
  "brief_description": "(Развёрнутое резюме 3-5 предложений, не более 600 символов)",
  "summary": "(Подробное описание)",
  "responsible_person": "(ФИО или организация)",
  "deadline": "(дата или срок)",
  "amount": "(сумма и валюта)"
}"""
    
    def _parse_llm_response(self, result_text: str, email_subject: str) -> Dict:
        """Парсинг ответа LLM"""
        try:
            # Ищем JSON в тексте
            start = result_text.find('{')
            end = result_text.rfind('}')
            
            if start != -1 and end != -1:
                json_str = result_text[start:end+1]
                json_str = json_str.replace('```json', '').replace('```', '').strip()
                data = json.loads(json_str)
            else:
                data = {}
        except:
            data = {}
        
        # Применяем те же правила очистки что и раньше
        brief = str(data.get('brief_description', '')).strip()
        if not brief:
            brief = str(data.get('summary', '')).strip()
        
        return {
            'document_type': self._normalize_doc_type(data.get('document_type', 'Договор')),
            'brief_description': brief[:1200] if brief else '',
            'description': str(data.get('summary', '')).strip()[:2000],
            'responsible_person': str(data.get('responsible_person', 'Не указано')).strip(),
            'deadline': str(data.get('deadline', 'Не указан')).strip(),
            'amount': str(data.get('amount', 'Не указана')).strip()
        }
