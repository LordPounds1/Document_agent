"""Base interface for input sources.

Defines the common contract for all document sources (Email, WhatsApp, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional


class DocumentType(Enum):
    """Supported document types."""
    PDF = 'pdf'
    DOCX = 'docx'
    DOC = 'doc'
    XLSX = 'xlsx'
    XLS = 'xls'
    TXT = 'txt'
    UNKNOWN = 'unknown'

    @classmethod
    def from_filename(cls, filename: str) -> 'DocumentType':
        """Determine document type from filename."""
        if not filename:
            return cls.UNKNOWN
        ext = Path(filename).suffix.lower().lstrip('.')
        mapping = {
            'pdf': cls.PDF,
            'docx': cls.DOCX,
            'doc': cls.DOC,
            'xlsx': cls.XLSX,
            'xls': cls.XLS,
            'txt': cls.TXT,
        }
        return mapping.get(ext, cls.UNKNOWN)


@dataclass
class Document:
    """Universal document representation from any source.

    This is the common data structure that flows through the processing pipeline,
    regardless of whether it came from Email, WhatsApp, or any other source.
    """
    # Identification
    id: str
    source_type: str  # 'email', 'whatsapp', etc.

    # Document data
    filename: str
    content: bytes | None = None  # Raw file content
    text: str | None = None       # Extracted text (if available)
    file_path: str | None = None  # Path to downloaded file
    document_type: DocumentType = DocumentType.UNKNOWN

    # Metadata
    sender: str = ''
    subject: str = ''  # Email subject or WhatsApp chat name
    received_at: datetime = field(default_factory=datetime.now)

    # Source-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Processing flags
    is_contract: bool = False
    confidence: float = 0.0

    def __post_init__(self):
        """Auto-detect document type from filename."""
        if self.document_type == DocumentType.UNKNOWN and self.filename:
            self.document_type = DocumentType.from_filename(self.filename)


class InputSource(ABC):
    """Abstract base class for document input sources.

    All document sources (Email, WhatsApp, API, etc.) must implement this interface
    to be compatible with the document processing pipeline.

    The pipeline is agnostic to the source - it only works with Document objects.
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'email', 'whatsapp')."""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the source.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the source."""
        pass

    @abstractmethod
    async def fetch_documents(
        self,
        limit: int = 100,
        since: datetime | None = None,
        **kwargs
    ) -> AsyncIterator[Document]:
        """Fetch documents from the source.

        Args:
            limit: Maximum number of documents to fetch.
            since: Only fetch documents received after this datetime.
            **kwargs: Source-specific parameters.

        Yields:
            Document objects ready for processing.
        """
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to the source."""
        pass

    async def __aenter__(self) -> 'InputSource':
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()


class SyncInputSource(ABC):
    """Synchronous version of InputSource for sources that don't support async.

    Provides the same interface but with synchronous methods.
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the source."""
        pass

    @abstractmethod
    def fetch_documents(
        self,
        limit: int = 100,
        since: datetime | None = None,
        **kwargs
    ) -> Iterator[Document]:
        """Fetch documents from the source."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if currently connected to the source."""
        pass

    def __enter__(self) -> 'SyncInputSource':
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()
