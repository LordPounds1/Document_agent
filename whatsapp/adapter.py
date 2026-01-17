"""WhatsApp adapter for document processing pipeline.

Integrates WhatsApp document extraction with the existing document processor.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Callable, List, Optional

from sources.base import Document, DocumentType, InputSource
from whatsapp.client import WhatsAppClient
from whatsapp.chat_iterator import ChatIterator, ChatInfo
from whatsapp.message_scanner import MessageScanner, MessageInfo
from whatsapp.downloader import DocumentDownloader

logger = logging.getLogger(__name__)


class WhatsAppPipeline:
    """High-level WhatsApp document extraction pipeline.

    Orchestrates the full workflow:
    1. Connect to WhatsApp Web
    2. Iterate through chats
    3. Scan for documents
    4. Download files
    5. Pass to document processor

    Example:
        ```python
        pipeline = WhatsAppPipeline()

        async with pipeline:
            async for doc in pipeline.extract_documents():
                if doc.is_contract:
                    result = processor.extract_contract_info(doc.text)
                    print(result)
        ```
    """

    def __init__(
        self,
        session_dir: str = '.whatsapp_session_playwright',
        downloads_dir: str = 'whatsapp_downloads',
        headless: bool = False
    ):
        """Initialize pipeline.

        Args:
            session_dir: Browser session directory.
            downloads_dir: Downloaded files directory.
            headless: Run browser without UI.
        """
        self.session_dir = session_dir
        self.downloads_dir = downloads_dir
        self.headless = headless

        self._client: WhatsAppClient | None = None
        self._iterator: ChatIterator | None = None
        self._scanner: MessageScanner | None = None
        self._downloader: DocumentDownloader | None = None

        # Callbacks
        self.on_chat_processed: Callable[[str, int | None, None]] = None
        self.on_document_found: Callable[[MessageInfo | None, None]] = None
        self.on_document_downloaded: Callable[[str | None, None]] = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to WhatsApp."""
        return self._client is not None and self._client.is_connected

    async def connect(self, timeout: int = 120) -> bool:
        """Connect to WhatsApp Web.

        Args:
            timeout: Seconds to wait for QR code scan.

        Returns:
            True if connected successfully.
        """
        self._client = WhatsAppClient(
            session_dir=self.session_dir,
            downloads_dir=self.downloads_dir,
            headless=self.headless
        )

        if not await self._client.start():
            return False

        if not await self._client.wait_for_login(timeout):
            await self._client.stop()
            return False

        # Initialize components
        page = self._client.page
        self._iterator = ChatIterator(page)
        self._scanner = MessageScanner(page)
        self._downloader = DocumentDownloader(page, self.downloads_dir)

        logger.info('WhatsApp pipeline connected')
        return True

    async def disconnect(self) -> None:
        """Disconnect from WhatsApp."""
        if self._client:
            await self._client.stop()
            self._client = None
            self._iterator = None
            self._scanner = None
            self._downloader = None
        logger.info('WhatsApp pipeline disconnected')

    async def extract_documents(
        self,
        chat_limit: int = 50,
        scroll_history: bool = True,
        contracts_only: bool = False
    ) -> AsyncIterator[Document]:
        """Extract documents from all WhatsApp chats.

        Args:
            chat_limit: Maximum chats to process.
            scroll_history: Scroll chat history to load old messages.
            contracts_only: Only yield documents classified as contracts.

        Yields:
            Document objects ready for processing.
        """
        if not self.is_connected:
            logger.error('Not connected to WhatsApp')
            return

        processed_chats = 0

        async for chat in self._iterator.iter_chats(scroll_count=5):
            if processed_chats >= chat_limit:
                break

            try:
                # Open chat
                if not await self._iterator.open_chat(chat.name):
                    logger.warning(f'Could not open chat: {chat.name}')
                    continue

                # Wait for chat to fully load
                await asyncio.sleep(1.5)

                # Verify chat is actually open
                page = self._client.page
                has_main = await page.evaluate('() => !!document.querySelector("#main")')
                if not has_main:
                    logger.warning(f'Chat {chat.name} did not open (no #main)')
                    continue

                # Scroll history if needed (but not too much - it can be slow)
                if scroll_history:
                    await self._iterator.scroll_chat_history(scroll_count=3)
                    await asyncio.sleep(0.5)

                # Find documents
                messages = await self._scanner.find_documents(chat.name)
                logger.debug(f'Found {len(messages)} document messages in {chat.name}')

                # Filter contracts if requested
                if contracts_only:
                    messages = [m for m in messages if m.is_contract]

                # Download and yield
                for msg in messages:
                    if self.on_document_found:
                        self.on_document_found(msg)

                    file_path = await self._downloader.download(msg)

                    if file_path:
                        if self.on_document_downloaded:
                            self.on_document_downloaded(file_path)

                        # Extract text from file
                        text = self._extract_text(file_path)

                        # Create Document
                        doc = Document(
                            id=msg.id,
                            source_type='whatsapp',
                            filename=msg.document_name or Path(file_path).name,
                            file_path=file_path,
                            text=text,
                            document_type=DocumentType.from_filename(file_path),
                            sender=msg.sender,
                            subject=chat.name,
                            received_at=msg.timestamp,
                            is_contract=msg.is_contract,
                            metadata={
                                'chat_name': chat.name,
                                'message_content': msg.content,
                                'is_group': chat.is_group,
                            }
                        )

                        yield doc

                processed_chats += 1

                if self.on_chat_processed:
                    self.on_chat_processed(chat.name, len(messages))

                logger.info(f'Processed chat: {chat.name} ({len(messages)} documents)')

            except Exception as e:
                logger.error(f'Error processing chat {chat.name}: {e}')
                continue

    def _extract_text(self, file_path: str) -> str:
        """Extract text from downloaded document.

        Args:
            file_path: Path to document file.

        Returns:
            Extracted text or empty string.
        """
        try:
            path = Path(file_path)
            suffix = path.suffix.lower()

            if suffix == '.txt':
                return path.read_text(encoding='utf-8')

            elif suffix == '.pdf':
                try:
                    import PyPDF2
                    with open(path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ''
                        for page in reader.pages:
                            text += page.extract_text() + '\n'
                        return text
                except ImportError:
                    logger.warning('PyPDF2 not installed')
                    return ''

            elif suffix in ['.docx', '.doc']:
                try:
                    import docx2txt
                    return docx2txt.process(str(path))
                except ImportError:
                    logger.warning('docx2txt not installed')
                    return ''

        except Exception as e:
            logger.error(f'Text extraction failed: {e}')

        return ''

    async def __aenter__(self) -> 'WhatsAppPipeline':
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()


class WhatsAppSource(InputSource):
    """WhatsApp as InputSource for unified pipeline.

    Implements the InputSource interface for the WhatsApp document extraction,
    making it fully compatible with the document processing pipeline.

    Example:
        ```python
        source = WhatsAppSource()

        async with source:
            async for doc in source.fetch_documents():
                process(doc)
        ```
    """

    def __init__(
        self,
        session_dir: str = '.whatsapp_session_playwright',
        downloads_dir: str = 'whatsapp_downloads',
        headless: bool = False
    ):
        """Initialize WhatsApp source.

        Args:
            session_dir: Browser session directory.
            downloads_dir: Downloaded files directory.
            headless: Run browser without UI.
        """
        self._pipeline = WhatsAppPipeline(
            session_dir=session_dir,
            downloads_dir=downloads_dir,
            headless=headless
        )

    @property
    def source_type(self) -> str:
        """Return source type identifier."""
        return 'whatsapp'

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._pipeline.is_connected

    async def connect(self, timeout: int = 120) -> bool:
        """Connect to WhatsApp Web.

        Args:
            timeout: Seconds to wait for login.

        Returns:
            True if connected.
        """
        return await self._pipeline.connect(timeout)

    async def disconnect(self) -> None:
        """Disconnect from WhatsApp."""
        await self._pipeline.disconnect()

    async def fetch_documents(
        self,
        limit: int = 100,
        since: datetime | None = None,
        contracts_only: bool = False,
        **kwargs
    ) -> AsyncIterator[Document]:
        """Fetch documents from WhatsApp chats.

        Args:
            limit: Maximum documents to fetch.
            since: Only fetch documents after this datetime.
            contracts_only: Only return documents classified as contracts.

        Yields:
            Document objects.
        """
        count = 0

        async for doc in self._pipeline.extract_documents(
            chat_limit=limit,
            contracts_only=contracts_only
        ):
            # Filter by date if specified
            if since and doc.received_at < since:
                continue

            count += 1
            if count > limit:
                break

            yield doc


# Note: WhatsAppSource is also available via sources.whatsapp_source
# for unified InputSource interface
