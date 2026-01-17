"""WhatsApp input source adapter.

Re-exports WhatsAppSource from the whatsapp module for unified interface.
"""

from collections.abc import AsyncIterator
from datetime import datetime

from sources.base import Document, InputSource
class WhatsAppSource(InputSource):
    """WhatsApp input source using Playwright browser automation.

    Adapts the WhatsApp pipeline to the unified InputSource interface.
    This allows the document processing pipeline to treat WhatsApp as just
    another source of documents.

    Example:
        ```python
        source = WhatsAppSource()

        async with source:
            async for doc in source.fetch_documents(limit=50):
                if doc.is_contract:
                    process_contract(doc)
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
            session_dir: Directory for browser session persistence.
            downloads_dir: Directory for downloaded files.
            headless: Run browser without UI (not recommended for first login).
        """
        # Lazy import to avoid circular dependency
        from whatsapp.adapter import WhatsAppPipeline
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
        """Check if connected to WhatsApp."""
        return self._pipeline.is_connected

    async def connect(self, timeout: int = 120) -> bool:
        """Connect to WhatsApp Web.

        On first run, a QR code will appear in the browser.
        Scan it with WhatsApp on your phone.
        Session is persisted for subsequent runs.

        Args:
            timeout: Seconds to wait for QR code scan.

        Returns:
            True if connected successfully.
        """
        return await self._pipeline.connect(timeout)

    async def disconnect(self) -> None:
        """Disconnect from WhatsApp and close browser."""
        await self._pipeline.disconnect()

    async def fetch_documents(  # type: ignore[override]
        self,
        limit: int = 100,
        since: datetime | None = None,
        contracts_only: bool = False,
        chat_limit: int = 50,
        scroll_history: bool = True,
        **kwargs
    ) -> AsyncIterator[Document]:
        """Fetch documents from WhatsApp chats.

        Iterates through chats, scans for documents (PDF, DOCX),
        downloads them, and yields Document objects.

        Args:
            limit: Maximum documents to fetch.
            since: Only fetch documents after this datetime.
            contracts_only: Only return documents classified as contracts.
            chat_limit: Maximum chats to process.
            scroll_history: Scroll chat history to load older messages.

        Yields:
            Document objects ready for processing.
        """
        count = 0

        async for doc in self._pipeline.extract_documents(
            chat_limit=chat_limit,
            scroll_history=scroll_history,
            contracts_only=contracts_only
        ):
            # Filter by date if specified
            if since and doc.received_at < since:
                continue

            count += 1
            if count > limit:
                break

            yield doc
