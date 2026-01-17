"""Unified input sources for document processing pipeline.

This module provides a common interface for different document sources:
- EmailSource: documents from email attachments
- WhatsAppSource: documents from WhatsApp chats
"""

from sources.base import InputSource, Document, DocumentType
from sources.email_source import EmailSource
from sources.whatsapp_source import WhatsAppSource
__all__ = [
    'InputSource',
    'Document',
    'DocumentType',
    'EmailSource',
    'WhatsAppSource',
]
