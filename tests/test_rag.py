"""Tests for core/rag.py."""

import pytest


class TestDocument:
    """Тесты для класса Document."""

    def test_document_creation(self):
        """Проверка создания документа."""
        from core.rag import Document
        doc = Document(
            content="Test content",
            metadata={'type': 'test'},
            score=0.5
        )
        assert doc.content == "Test content"
        assert doc.metadata['type'] == 'test'
        assert doc.score == 0.5

    def test_document_default_score(self):
        """Проверка значения score по умолчанию."""
        from core.rag import Document
        doc = Document(content="Test", metadata={})
        assert doc.score == 0.0


class TestSimpleRAG:
    """Тесты для класса SimpleRAG."""

    def test_rag_initialization(self, temp_templates_dir):
        """Проверка инициализации RAG."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        assert rag is not None
        assert rag.documents == []

    def test_legal_synonyms_exist(self, temp_templates_dir):
        """Проверка наличия юридических синонимов."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        assert len(rag.LEGAL_SYNONYMS) > 0
        assert 'договор' in rag.LEGAL_SYNONYMS

    def test_contract_keywords_exist(self, temp_templates_dir):
        """Проверка наличия ключевых слов договора."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        assert len(rag.CONTRACT_KEYWORDS) > 0
        assert 'договор' in rag.CONTRACT_KEYWORDS

    def test_expand_query_with_synonyms(self, temp_templates_dir):
        """Проверка расширения запроса синонимами."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        expanded = rag.expand_query("договор аренды")
        assert "контракт" in expanded or "соглашение" in expanded

    def test_expand_query_no_synonyms(self, temp_templates_dir):
        """Проверка запроса без синонимов."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        original = "привет мир"
        expanded = rag.expand_query(original)
        assert expanded == original

    def test_normalize_text(self, temp_templates_dir):
        """Проверка нормализации текста."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        text = "  Привет   МИРА!  "
        normalized = rag.normalize_text(text)
        assert normalized == "привет мира"

    def test_is_contract_positive(self, temp_templates_dir, sample_contract_text):
        """Проверка определения договора (положительный случай)."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        is_contract, confidence = rag.is_contract(sample_contract_text)
        assert is_contract is True
        assert confidence > 0.4

    def test_is_contract_negative(self, temp_templates_dir, sample_non_contract_text):
        """Проверка определения договора (отрицательный случай)."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        is_contract, confidence = rag.is_contract(sample_non_contract_text)
        assert is_contract is False
        assert confidence < 0.4

    def test_get_stats(self, temp_templates_dir):
        """Проверка получения статистики."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        stats = rag.get_stats()
        assert 'total_templates' in stats
        assert 'synonyms_count' in stats
        assert 'keywords_count' in stats
        assert 'vector_search_enabled' in stats

    def test_retrieve_empty_documents(self, temp_templates_dir):
        """Проверка поиска при пустом списке документов."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        rag.clear_index()  # Очищаем индекс для чистого теста
        
        results = rag.retrieve("договор аренды", k=5)
        assert results == []

    def test_search_empty_documents(self, temp_templates_dir):
        """Проверка полного поиска при пустом списке документов."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        rag.clear_index()  # Очищаем индекс для чистого теста
        
        results = rag.search("договор аренды", k=5)
        assert results == []

    def test_filter_relevant(self, temp_templates_dir):
        """Проверка фильтрации по релевантности."""
        from core.rag import SimpleRAG, Document
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        docs = [
            Document(content="doc1", metadata={}, score=0.8),
            Document(content="doc2", metadata={}, score=0.05),
            Document(content="doc3", metadata={}, score=0.3),
        ]
        
        filtered = rag.filter_relevant(docs, min_score=0.1)
        assert len(filtered) == 2
        assert all(d.score >= 0.1 for d in filtered)

    def test_add_document(self, temp_templates_dir):
        """Проверка добавления документа."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        initial_count = len(rag.documents)
        result = rag.add_document("Test content", {'type': 'test'})
        
        assert result is True
        assert len(rag.documents) == initial_count + 1

    def test_add_empty_document(self, temp_templates_dir):
        """Проверка добавления пустого документа."""
        from core.rag import SimpleRAG
        rag = SimpleRAG(templates_dir=str(temp_templates_dir))
        
        result = rag.add_document("", {'type': 'test'})
        assert result is False
