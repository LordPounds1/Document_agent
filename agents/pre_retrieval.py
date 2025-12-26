"""Pre-Retrieval Pipeline - обработка пользовательского запроса перед поиском в базе"""

import logging
import re
from typing import List, Dict, Optional
from langchain.llms.base import LLM

logger = logging.getLogger(__name__)


class PreRetrievalPipeline:
    """
    Pre-retrieval обработка запроса для улучшения качества поиска.
    Использует две техники:
    1. Query Expansion - расширение запроса дополнительными вариантами
    2. Query Rewriting - переписывание запроса для лучшего поиска
    """
    
    def __init__(self, llm_client: Optional[LLM] = None):
        """
        Инициализация pipeline
        
        Args:
            llm_client: LLM клиент для переписывания запроса (опционально)
        """
        self.llm_client = llm_client
    
    def process_query(self, query: str, method: str = "expansion") -> Dict[str, any]:
        """
        Главная функция обработки запроса
        
        Args:
            query: Исходный запрос пользователя
            method: Метод обработки - "expansion", "rewriting" или "hybrid"
        
        Returns:
            {
                'original': исходный запрос,
                'processed': основной обработанный запрос,
                'variants': список вариантов запроса,
                'keywords': извлеченные ключевые слова,
                'method': использованный метод
            }
        """
        logger.info(f"[PRE-RETRIEVAL] Обработка запроса: '{query}' (метод: {method})")
        
        result = {
            'original': query,
            'processed': query,
            'variants': [query],
            'keywords': self._extract_keywords(query),
            'method': method
        }
        
        if method == "expansion":
            result['variants'] = self._query_expansion(query)
            result['processed'] = result['variants'][0] if result['variants'] else query
        
        elif method == "rewriting":
            if self.llm_client:
                result['processed'] = self._query_rewriting_with_llm(query)
                result['variants'] = [result['processed']]
            else:
                # Fallback: простое переписывание без LLM
                result['processed'] = self._query_rewriting_simple(query)
                result['variants'] = [result['processed']]
        
        elif method == "hybrid":
            # Комбинируем оба метода
            expanded = self._query_expansion(query)
            if self.llm_client:
                rewritten = self._query_rewriting_with_llm(query)
                result['variants'] = expanded + [rewritten]
                result['processed'] = rewritten
            else:
                result['variants'] = expanded
                result['processed'] = expanded[0] if expanded else query
        
        logger.info(f"  Варианты запроса: {len(result['variants'])}")
        logger.info(f"  Ключевые слова: {result['keywords']}")
        
        return result
    
    def _extract_keywords(self, query: str) -> List[str]:
        """
        Извлечение ключевых слов из запроса
        
        Удаляет стоп-слова и оставляет только значимые термины
        """
        # Русские стоп-слова
        stop_words = {
            'и', 'или', 'но', 'что', 'где', 'когда', 'как', 'почему',
            'в', 'на', 'при', 'для', 'с', 'о', 'об', 'по', 'у', 'за',
            'к', 'от', 'до', 'из', 'через', 'без', 'под', 'над',
            'это', 'то', 'все', 'всё', 'некоторый', 'любой', 'некий',
            'мне', 'тебе', 'ему', 'нам', 'вам', 'им',
            'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они',
            'а', 'так', 'да', 'нет', 'вот', 'вне',
            'словно', 'ибо', 'хоть', 'ведь', 'уж', 'уже',
            'бы', 'ль', 'же', 'вам', 'тоже'
        }
        
        # Токенизируем
        words = re.findall(r'\b\w+\b', query.lower())
        
        # Фильтруем стоп-слова и короткие слова
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return keywords
    
    def _query_expansion(self, query: str) -> List[str]:
        """
        Query Expansion - расширение запроса вариантами
        
        Генерирует альтернативные формулировки запроса для лучшего поиска
        """
        variants = [query]  # Оригинал всегда первый
        
        # Извлекаем ключевые слова
        keywords = self._extract_keywords(query)
        
        if not keywords:
            return variants
        
        # Вариант 1: Только ключевые слова
        if len(keywords) > 1:
            keyword_only = ' '.join(keywords)
            if keyword_only != query:
                variants.append(keyword_only)
        
        # Вариант 2: Синонимичные выражения
        synonyms_variants = self._generate_synonyms_variants(query, keywords)
        variants.extend(synonyms_variants)
        
        # Вариант 3: Расширение с контекстом договора (если применимо)
        if any(word in query.lower() for word in ['договор', 'контракт', 'соглашение']):
            legal_expanded = self._expand_legal_query(query)
            if legal_expanded:
                variants.append(legal_expanded)
        
        # Вариант 4: Поиск с синонимами (простые замены)
        synonym_expanded = self._simple_synonym_expansion(query)
        if synonym_expanded != query:
            variants.append(synonym_expanded)
        
        # Удаляем дубликаты сохраняя порядок
        seen = set()
        unique_variants = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                unique_variants.append(v)
        
        logger.debug(f"Query Expansion создал {len(unique_variants)} вариантов")
        return unique_variants
    
    def _generate_synonyms_variants(self, query: str, keywords: List[str]) -> List[str]:
        """Генерирование вариантов с синонимами"""
        # Простой словарь синонимов для юридических документов
        synonyms = {
            'договор': ['контракт', 'соглашение', 'соглас'],
            'контракт': ['договор', 'соглашение'],
            'сумма': ['стоимость', 'сумма денег', 'цена'],
            'срок': ['дата', 'период', 'временной промежуток'],
            'клиент': ['заказчик', 'партнер', 'сторона'],
            'поставщик': ['продавец', 'исполнитель', 'поставщик услуг'],
            'оплата': ['расчет', 'платеж', 'счет'],
            'условие': ['пункт', 'требование', 'положение']
        }
        
        variants = []
        for keyword in keywords:
            if keyword in synonyms:
                for synonym in synonyms[keyword]:
                    variant = query.replace(keyword, synonym, 1)
                    if variant != query and variant not in variants:
                        variants.append(variant)
        
        return variants
    
    def _expand_legal_query(self, query: str) -> Optional[str]:
        """Специальное расширение для юридических запросов"""
        legal_terms = {
            'договор поставки': 'договор поставки товаров условия сроки',
            'договор оказания услуг': 'договор оказания услуг стоимость сроки',
            'акт выполнения': 'акт выполненных работ оказанных услуг',
            'допсоглашение': 'дополнительное соглашение к договору'
        }
        
        for term, expansion in legal_terms.items():
            if term in query.lower():
                return expansion
        
        return None
    
    def _simple_synonym_expansion(self, query: str) -> str:
        """Простая замена часто встречающихся термонов"""
        replacements = {
            'сумма': 'стоимость',
            'срок': 'дата',
            'условие': 'пункт',
            'требование': 'обязательство'
        }
        
        expanded = query
        for word, replacement in replacements.items():
            if word in query.lower():
                # Заменяем с сохранением регистра
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                expanded = pattern.sub(replacement, expanded, count=1)
        
        return expanded
    
    def _query_rewriting_simple(self, query: str) -> str:
        """
        Простое переписывание запроса без LLM
        Очищает и нормализует запрос для лучшего поиска
        """
        # Нормализуем пунктуацию
        rewritten = query.strip()
        rewritten = re.sub(r'\s+', ' ', rewritten)  # Удаляем лишние пробелы
        
        # Добавляем контекст документа если нужно
        if not any(word in rewritten.lower() for word in ['договор', 'документ']):
            rewritten = f"документ {rewritten}"
        
        logger.debug(f"Simple rewriting: '{query}' → '{rewritten}'")
        return rewritten
    
    def _query_rewriting_with_llm(self, query: str) -> str:
        """
        Переписывание запроса с помощью LLM для оптимизации поиска
        LLM переформулирует запрос так, чтобы лучше соответствовать структуре базы
        """
        if not self.llm_client:
            return query
        
        prompt = f"""Переформулируй следующий запрос так, чтобы он был оптимален для поиска в базе юридических документов.
Запрос должен быть точнее, яснее и содержать ключевые термины.

Исходный запрос: {query}

Переформулированный запрос:"""
        
        try:
            response = self.llm_client(
                prompt,
                max_tokens=150,
                temperature=0.3,
            )
            
            if isinstance(response, dict):
                rewritten = response.get('choices', [{}])[0].get('text', '').strip()
            else:
                rewritten = str(response).strip()
            
            logger.debug(f"LLM rewriting: '{query}' → '{rewritten}'")
            return rewritten if rewritten else query
            
        except Exception as e:
            logger.warning(f"Ошибка переписывания с LLM: {e}")
            return query
    
    def get_search_queries(self, processed: Dict) -> List[str]:
        """
        Получение всех вариантов запроса для поиска
        Использует варианты из pre-retrieval обработки
        
        Args:
            processed: Результат process_query()
        
        Returns:
            Отсортированный список уникальных запросов для поиска
        """
        # Берем варианты и добавляем версии с ключевыми словами
        queries = list(processed['variants'])
        
        # Добавляем поиск по каждому ключевому слову отдельно
        for keyword in processed['keywords'][:5]:  # Max 5 ключевых слов
            if keyword not in ' '.join(queries):
                queries.append(keyword)
        
        return queries
