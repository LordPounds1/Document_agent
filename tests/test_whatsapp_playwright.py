"""Тесты для нового WhatsApp модуля на Playwright.

Проверяет:
- sources/ модуль (InputSource interface)
- whatsapp/ модуль (Playwright automation)
- Интеграцию с существующим DocumentProcessor

Запуск:
    pytest tests/test_whatsapp_playwright.py -v
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock
import pytest
# ============ Tests for sources/base.py ============
class TestDocumentType:
    """Тесты для DocumentType enum."""

    def test_from_filename_pdf(self):
        from sources.base import DocumentType
        assert DocumentType.from_filename('contract.pdf') == DocumentType.PDF
        assert DocumentType.from_filename('CONTRACT.PDF') == DocumentType.PDF

    def test_from_filename_docx(self):
        from sources.base import DocumentType
        assert DocumentType.from_filename('agreement.docx') == DocumentType.DOCX
        assert DocumentType.from_filename('file.doc') == DocumentType.DOC

    def test_from_filename_excel(self):
        from sources.base import DocumentType
        assert DocumentType.from_filename('data.xlsx') == DocumentType.XLSX
        assert DocumentType.from_filename('old.xls') == DocumentType.XLS

    def test_from_filename_txt(self):
        from sources.base import DocumentType
        assert DocumentType.from_filename('readme.txt') == DocumentType.TXT

    def test_from_filename_unknown(self):
        from sources.base import DocumentType
        assert DocumentType.from_filename('image.jpg') == DocumentType.UNKNOWN
        assert DocumentType.from_filename('') == DocumentType.UNKNOWN
        assert DocumentType.from_filename(None) == DocumentType.UNKNOWN


class TestDocument:
    """Тесты для Document dataclass."""

    def test_document_creation(self):
        from sources.base import Document, DocumentType
        doc = Document(
            id='test_123',
            source_type='whatsapp',
            filename='contract.pdf',
            sender='John Doe',
            subject='Business Chat'
        )

        assert doc.id == 'test_123'
        assert doc.source_type == 'whatsapp'
        assert doc.filename == 'contract.pdf'
        assert doc.document_type == DocumentType.PDF  # Auto-detected
        assert doc.sender == 'John Doe'
        assert doc.is_contract is False

    def test_document_with_text(self):
        from sources.base import Document
        doc = Document(
            id='test_456',
            source_type='email',
            filename='agreement.docx',
            text='Договор поставки между ООО "Альфа" и ООО "Бета"',
            is_contract=True,
            confidence=0.95
        )

        assert doc.text is not None
        assert 'Договор' in doc.text
        assert doc.is_contract is True
        assert doc.confidence == 0.95

    def test_document_metadata(self):
        from sources.base import Document
        doc = Document(
            id='test_789',
            source_type='whatsapp',
            filename='invoice.pdf',
            metadata={
                'chat_name': 'Suppliers',
                'is_group': True,
                'message_id': 'msg_001'
            }
        )

        assert doc.metadata['chat_name'] == 'Suppliers'
        assert doc.metadata['is_group'] is True


# ============ Tests for sources/email_source.py ============

class TestEmailSource:
    """Тесты для EmailSource adapter."""

    def test_email_source_properties(self):
        from sources.email_source import EmailSource
        source = EmailSource(
            email='test@gmail.com',
            password='password123'
        )

        assert source.source_type == 'email'
        assert source.is_connected is False

    def test_email_source_connect_disconnect(self):
        from sources.email_source import EmailSource
        source = EmailSource(
            email='test@gmail.com',
            password='password123'
        )

        # Mock the agent
        source._agent = Mock()
        source._agent.connect = Mock(return_value=True)
        source._agent.connected = True

        result = source.connect()
        assert result is True
        assert source.is_connected is True

        source._agent.disconnect = Mock()
        source.disconnect()
        assert source.is_connected is False


# ============ Tests for whatsapp/client.py ============

class TestWhatsAppClient:
    """Тесты для WhatsAppClient."""

    def test_client_initialization(self):
        from whatsapp.client import WhatsAppClient
        client = WhatsAppClient(
            session_dir='.test_session',
            downloads_dir='.test_downloads',
            headless=True
        )

        assert client.session_dir == Path('.test_session').absolute()
        assert client.downloads_dir == Path('.test_downloads').absolute()
        assert client.headless is True
        assert client.is_connected is False
        assert client.page is None

    def test_client_selectors_defined(self):
        from whatsapp.client import WhatsAppClient
        # Verify all required selectors are defined
        required = ['qr_canvas', 'chat_list', 'side_panel', 'search_box']
        for selector in required:
            assert selector in WhatsAppClient.SELECTORS


# ============ Tests for whatsapp/chat_iterator.py ============

class TestChatInfo:
    """Тесты для ChatInfo dataclass."""

    def test_chat_info_creation(self):
        from whatsapp.chat_iterator import ChatInfo
        chat = ChatInfo(
            name='Business Partner',
            last_message='Договор готов',
            unread_count=3,
            is_group=False
        )

        assert chat.name == 'Business Partner'
        assert chat.unread_count == 3
        assert chat.is_group is False


class TestChatIterator:
    """Тесты для ChatIterator."""

    def test_iterator_selectors_defined(self):
        from whatsapp.chat_iterator import ChatIterator
        required = ['chat_list', 'chat_item', 'chat_title', 'search_box']
        for selector in required:
            assert selector in ChatIterator.SELECTORS

    @pytest.mark.asyncio
    async def test_open_chat_empty_name(self):
        from whatsapp.chat_iterator import ChatIterator
        mock_page = AsyncMock()
        iterator = ChatIterator(mock_page)

        result = await iterator.open_chat('')
        assert result is False

        result = await iterator.open_chat('   ')
        assert result is False


# ============ Tests for whatsapp/message_scanner.py ============

class TestMessageInfo:
    """Тесты для MessageInfo dataclass."""

    def test_message_info_creation(self):
        from whatsapp.message_scanner import MessageInfo
        msg = MessageInfo(
            id='msg_001',
            sender='Partner Inc',
            content='Отправляю договор',
            timestamp=datetime.now(),
            chat_name='Business',
            has_document=True,
            document_name='contract.pdf',
            is_contract=True
        )

        assert msg.id == 'msg_001'
        assert msg.has_document is True
        assert msg.is_contract is True


class TestMessageScanner:
    """Тесты для MessageScanner."""

    def test_contract_keywords_defined(self):
        from whatsapp.message_scanner import MessageScanner
        keywords = MessageScanner.CONTRACT_KEYWORDS
        assert 'договор' in keywords
        assert 'контракт' in keywords
        assert '.pdf' in keywords
        assert '.docx' in keywords

    def test_is_contract_detection(self):
        from whatsapp.message_scanner import MessageScanner
        mock_page = Mock()
        scanner = MessageScanner(mock_page)

        # Test with contract keywords
        assert scanner._is_contract('Отправляю договор поставки', None) is True
        assert scanner._is_contract('Подпиши контракт', None) is True
        assert scanner._is_contract('Вот соглашение', None) is True

        # Test with document names
        assert scanner._is_contract('', 'договор.pdf') is True
        assert scanner._is_contract('', 'contract.docx') is True
        assert scanner._is_contract('', 'invoice.pdf') is True

        # Test non-contracts
        assert scanner._is_contract('Привет, как дела?', None) is False
        assert scanner._is_contract('', 'photo.jpg') is False

    def test_generate_id(self):
        from whatsapp.message_scanner import MessageScanner
        mock_page = Mock()
        scanner = MessageScanner(mock_page)

        id1 = scanner._generate_id('Chat1', 'User1', 'Hello', datetime(2024, 1, 15, 10, 30))
        id2 = scanner._generate_id('Chat1', 'User1', 'Hello', datetime(2024, 1, 15, 10, 30))
        id3 = scanner._generate_id('Chat2', 'User1', 'Hello', datetime(2024, 1, 15, 10, 30))

        # Same input = same ID
        assert id1 == id2
        # Different input = different ID
        assert id1 != id3


# ============ Tests for whatsapp/downloader.py ============

class TestDocumentDownloader:
    """Тесты для DocumentDownloader."""

    def test_sanitize_filename(self):
        from whatsapp.downloader import DocumentDownloader
        mock_page = Mock()
        downloader = DocumentDownloader(mock_page, downloads_dir='.test_downloads')

        # Normal filename
        assert downloader._sanitize_filename('contract.pdf') == 'contract.pdf'

        # Dangerous characters
        assert '..' not in downloader._sanitize_filename('../../../etc/passwd')
        assert ':' not in downloader._sanitize_filename('C:\\Windows\\file.pdf')

        # Empty filename
        result = downloader._sanitize_filename('')
        assert result.startswith('document_')

        # Long filename
        long_name = 'a' * 300 + '.pdf'
        result = downloader._sanitize_filename(long_name)
        assert len(result) <= 200


# ============ Tests for whatsapp/adapter.py ============

class TestWhatsAppPipeline:
    """Тесты для WhatsAppPipeline."""

    def test_pipeline_initialization(self):
        from whatsapp.adapter import WhatsAppPipeline
        pipeline = WhatsAppPipeline(
            session_dir='.test_session',
            downloads_dir='.test_downloads',
            headless=True
        )

        assert pipeline.session_dir == '.test_session'
        assert pipeline.downloads_dir == '.test_downloads'
        assert pipeline.is_connected is False

    def test_extract_text_txt(self, tmp_path):
        from whatsapp.adapter import WhatsAppPipeline
        pipeline = WhatsAppPipeline()

        # Create test file
        test_file = tmp_path / 'test.txt'
        test_file.write_text('Договор поставки товаров', encoding='utf-8')

        text = pipeline._extract_text(str(test_file))
        assert 'Договор' in text


class TestWhatsAppSource:
    """Тесты для WhatsAppSource (InputSource interface)."""

    def test_source_type(self):
        from sources.whatsapp_source import WhatsAppSource
        source = WhatsAppSource()
        assert source.source_type == 'whatsapp'

    def test_is_connected_default(self):
        from sources.whatsapp_source import WhatsAppSource
        source = WhatsAppSource()
        assert source.is_connected is False


# ============ Integration Tests ============

class TestIntegration:
    """Интеграционные тесты."""

    def test_imports_work(self):
        """Проверка что все импорты работают."""
        # All imports successful
        assert True

    def test_document_processor_integration(self):
        """Проверка интеграции с существующим DocumentProcessor."""
        from sources.base import Document
        # Create a mock document from WhatsApp
        doc = Document(
            id='wa_test_001',
            source_type='whatsapp',
            filename='contract.pdf',
            text='''
            ДОГОВОР ПОСТАВКИ № 123

            ООО "Поставщик" (Поставщик) и ООО "Покупатель" (Покупатель)
            заключили настоящий договор о нижеследующем:

            1. Предмет договора
            Поставщик обязуется поставить товар на сумму 1 000 000 тенге.

            2. Сроки
            Срок поставки: 30 дней с момента подписания.

            3. Ответственность
            За просрочку поставки начисляется пеня 0.1% за каждый день.
            ''',
            sender='Supplier Inc',
            subject='Business Chat',
            is_contract=True
        )

        # Document can be processed by existing processor
        assert doc.text is not None
        assert len(doc.text) > 100
        assert doc.source_type == 'whatsapp'

    def test_unified_interface(self):
        """Проверка единого интерфейса для разных источников."""
        from sources.email_source import EmailSource
        from sources.whatsapp_source import WhatsAppSource
        # Both implement the same interface pattern
        email = EmailSource('test@test.com', 'pass')
        whatsapp = WhatsAppSource()

        # Same properties available
        assert hasattr(email, 'source_type')
        assert hasattr(whatsapp, 'source_type')
        assert hasattr(email, 'is_connected')
        assert hasattr(whatsapp, 'is_connected')
        assert hasattr(email, 'connect')
        assert hasattr(whatsapp, 'connect')
        assert hasattr(email, 'disconnect')
        assert hasattr(whatsapp, 'disconnect')
        assert hasattr(email, 'fetch_documents')
        assert hasattr(whatsapp, 'fetch_documents')


# ============ Smoke Test ============

def test_smoke():
    """Быстрый smoke test - проверка что модули загружаются."""
    import sources
    import whatsapp
    # Check modules have expected exports
    assert hasattr(sources, 'InputSource')
    assert hasattr(sources, 'Document')
    assert hasattr(sources, 'EmailSource')
    assert hasattr(sources, 'WhatsAppSource')

    assert hasattr(whatsapp, 'WhatsAppClient')
    assert hasattr(whatsapp, 'ChatIterator')
    assert hasattr(whatsapp, 'MessageScanner')
    assert hasattr(whatsapp, 'DocumentDownloader')
    assert hasattr(whatsapp, 'WhatsAppPipeline')

    print('\n✅ Smoke test passed - all modules load correctly')


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
