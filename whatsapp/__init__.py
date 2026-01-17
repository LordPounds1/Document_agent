"""WhatsApp document source module using Playwright.

This module provides async WhatsApp Web automation for extracting documents
from chats. It uses Playwright for browser automation.
Components:
- WhatsAppClient: Browser launch and QR auth
- ChatIterator: Navigate through all chats
- MessageScanner: Find documents in chat history
- DocumentDownloader: Download PDF/DOCX files
- WhatsAppPipeline: Integration with document pipeline
- WhatsAppMonitor: Background monitoring for new documents
"""

from whatsapp.adapter import WhatsAppPipeline
from whatsapp.chat_iterator import ChatIterator
from whatsapp.client import WhatsAppClient
from whatsapp.downloader import DocumentDownloader
from whatsapp.message_scanner import MessageScanner
from whatsapp.monitor import (
    WhatsAppMonitor,
    create_monitor,
    get_monitor,
    stop_monitor,
)

__all__ = [
    'WhatsAppClient',
    'ChatIterator',
    'MessageScanner',
    'DocumentDownloader',
    'WhatsAppPipeline',
    'WhatsAppMonitor',
    'get_monitor',
    'create_monitor',
    'stop_monitor',
]
