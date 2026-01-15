"""WhatsApp document source module using Playwright.

This module provides async WhatsApp Web automation for extracting documents
from chats. It uses Playwright for browser automation.

Components:
- WhatsAppClient: Browser launch and QR auth
- ChatIterator: Navigate through all chats
- MessageScanner: Find documents in chat history  
- DocumentDownloader: Download PDF/DOCX files
- WhatsAppAdapter: Integration with document pipeline
"""

from whatsapp.client import WhatsAppClient
from whatsapp.chat_iterator import ChatIterator
from whatsapp.message_scanner import MessageScanner
from whatsapp.downloader import DocumentDownloader
from whatsapp.adapter import WhatsAppPipeline

__all__ = [
    'WhatsAppClient',
    'ChatIterator',
    'MessageScanner',
    'DocumentDownloader',
    'WhatsAppPipeline',
]
