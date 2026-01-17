"""Email input source adapter.

Wraps the existing EmailAgent to conform to the InputSource interface.
"""

from collections.abc import Iterator
from datetime import datetime
import logging

from agents.email_agent import EmailAgent
from sources.base import Document, DocumentType, SyncInputSource
logger = logging.getLogger(__name__)


class EmailSource(SyncInputSource):
    """Email input source using IMAP.

    Adapts the existing EmailAgent to the unified InputSource interface.
    This allows the document processing pipeline to treat email as just
    another source of documents.

    Example:
        ```python
        source = EmailSource(email='user@gmail.com', password='app_password')

        with source:
            for doc in source.fetch_documents(limit=50):
                if doc.is_contract:
                    process_contract(doc)
        ```
    """

    def __init__(
        self,
        email: str,
        password: str,
        folder: str = 'INBOX'
    ):
        """Initialize email source.

        Args:
            email: Email address.
            password: Password or app-specific password.
            folder: IMAP folder to read from (default: INBOX).
        """
        self._email = email
        self._password = password
        self._folder = folder
        self._agent = EmailAgent()
        self._connected = False

    @property
    def source_type(self) -> str:
        """Return source type identifier."""
        return 'email'

    @property
    def is_connected(self) -> bool:
        """Check connection status."""
        return self._connected and self._agent.connected

    def connect(self) -> bool:
        """Connect to email server."""
        try:
            self._connected = self._agent.connect(self._email, self._password)
            if self._connected:
                logger.info(f'EmailSource connected: {self._email}')
            return self._connected
        except Exception as e:
            logger.error(f'EmailSource connection failed: {e}')
            return False

    def disconnect(self) -> None:
        """Disconnect from email server."""
        try:
            self._agent.disconnect()
            self._connected = False
            logger.info('EmailSource disconnected')
        except Exception as e:
            logger.warning(f'EmailSource disconnect error: {e}')

    def fetch_documents(
        self,
        limit: int = 100,
        since: datetime | None = None,
        unread_only: bool = False,
        **kwargs
    ) -> Iterator[Document]:
        """Fetch documents from email attachments.

        Args:
            limit: Maximum number of emails to process.
            since: Only process emails received after this datetime.
            unread_only: Only process unread emails.

        Yields:
            Document objects for each valid attachment.
        """
        if not self.is_connected:
            logger.warning('EmailSource not connected')
            return

        # Fetch emails
        emails = self._agent.fetch_emails(
            folder=self._folder,
            unread_only=unread_only,
            limit=limit
        )

        for email_data in emails:
            # Filter by date if specified
            email_date = email_data.get('date', datetime.now())
            if since and email_date < since:
                continue

            # Process attachments
            for attachment in email_data.get('attachments', []):
                filename = attachment.get('filename', '')

                # Only process document types
                doc_type = DocumentType.from_filename(filename)
                if doc_type == DocumentType.UNKNOWN:
                    continue

                # Extract text from attachment
                text = self._agent.get_attachment_text(attachment)

                # Create Document
                doc = Document(
                    id=f"email_{email_data.get('id', '')}_{filename}",
                    source_type=self.source_type,
                    filename=filename,
                    content=attachment.get('content'),
                    text=text,
                    document_type=doc_type,
                    sender=email_data.get('from', ''),
                    subject=email_data.get('subject', ''),
                    received_at=email_date,
                    metadata={
                        'email_id': email_data.get('id'),
                        'message_id': email_data.get('message_id'),
                        'body': email_data.get('body', '')[:500],
                        'content_type': attachment.get('content_type'),
                        'size': attachment.get('size', 0),
                    }
                )

                yield doc

            # Also check email body for inline contracts
            body = email_data.get('body', '')
            if body and len(body) > 100:
                doc = Document(
                    id=f"email_{email_data.get('id', '')}_body",
                    source_type=self.source_type,
                    filename='email_body.txt',
                    text=body,
                    document_type=DocumentType.TXT,
                    sender=email_data.get('from', ''),
                    subject=email_data.get('subject', ''),
                    received_at=email_date,
                    metadata={
                        'email_id': email_data.get('id'),
                        'message_id': email_data.get('message_id'),
                        'is_body': True,
                    }
                )
                yield doc
