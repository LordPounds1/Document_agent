"""Tests for processors/document.py."""

import pytest
from unittest.mock import Mock, patch


class TestDocumentProcessor:
    """Тесты для класса DocumentProcessor."""

    def test_processor_initialization(self):
        """Проверка инициализации процессора."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )
        assert processor is not None
        assert processor._llm_initialized is False
        assert processor._rag_initialized is False

    def test_is_contract_positive(self, sample_contract_text):
        """Проверка определения договора (положительный)."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        is_contract, confidence = processor.is_contract(sample_contract_text)
        assert is_contract is True

    def test_is_contract_negative(self, sample_non_contract_text):
        """Проверка определения договора (отрицательный)."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        is_contract, confidence = processor.is_contract(sample_non_contract_text)
        assert is_contract is False

    def test_extract_basic_info_contract_type_arenda(self):
        """Проверка определения типа договора аренды."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        text = "Договор аренды помещения между сторонами"
        result = processor._extract_basic_info(text)

        assert result['document_type'] == 'Договор аренды'

    def test_extract_basic_info_contract_type_postavka(self):
        """Проверка определения типа договора поставки."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        text = "Договор поставки товаров между сторонами"
        result = processor._extract_basic_info(text)

        assert result['document_type'] == 'Договор поставки'

    def test_extract_basic_info_contract_type_uslugi(self):
        """Проверка определения типа договора услуг."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        text = "Договор оказания услуг между сторонами"
        result = processor._extract_basic_info(text)

        assert result['document_type'] == 'Договор оказания услуг'

    def test_extract_basic_info_finds_amount(self):
        """Проверка извлечения суммы из текста."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        text = "Стоимость составляет 500000 тенге"
        result = processor._extract_basic_info(text)

        assert 'тенге' in result['amount'].lower() or '500000' in result['amount']

    def test_extract_basic_info_finds_date(self):
        """Проверка извлечения даты из текста."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        text = "Договор от 01.01.2026 между сторонами"
        result = processor._extract_basic_info(text)

        assert result['date'] == '01.01.2026'

    def test_extract_basic_info_has_processed_at(self):
        """Проверка наличия даты обработки."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        result = processor._extract_basic_info("Test text")
        assert 'processed_at' in result
        assert result['processed_at'] is not None

    def test_process_email_with_contract(self, mock_email_data, sample_contract_text):
        """Проверка обработки email с договором."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        result = processor.process_email_with_contract(
            mock_email_data,
            sample_contract_text
        )

        assert 'email_id' in result
        assert 'email_from' in result
        assert 'document_type' in result
        assert 'summary' in result
        assert result['email_from'] == 'sender@example.com'

    def test_close_without_initialization(self):
        """Проверка закрытия без инициализации LLM."""
        from processors.document import DocumentProcessor
        processor = DocumentProcessor(
            model_path="fake_model.gguf",
            templates_dir="templates"
        )

        # Не должно вызывать ошибку
        processor.close()
        assert processor.llm is None
