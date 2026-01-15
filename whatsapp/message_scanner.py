"""Message scanner for WhatsApp Web.

Scans chat messages to find documents (PDF, DOCX, etc.).
"""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Page, ElementHandle
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None
    ElementHandle = None


@dataclass
class MessageInfo:
    """Information about a WhatsApp message."""
    id: str
    sender: str
    content: str
    timestamp: datetime
    chat_name: str
    
    # Document info
    has_document: bool = False
    document_name: Optional[str] = None
    document_element: Optional[ElementHandle] = None
    
    # Classification
    is_contract: bool = False
    is_outgoing: bool = False
    
    # Extra metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageScanner:
    """Scans WhatsApp messages for documents.
    
    Provides methods to:
    - Find all messages in current chat
    - Detect document attachments
    - Filter by document type (PDF, DOCX)
    - Classify potential contracts
    
    Example:
        ```python
        scanner = MessageScanner(page)
        
        messages = await scanner.scan_messages(chat_name='Supplier Inc')
        documents = [m for m in messages if m.has_document]
        contracts = [m for m in messages if m.is_contract]
        ```
    """
    
    # Multiple selector variants for WhatsApp Web
    SELECTORS = {
        'message_list': '[data-testid="conversation-panel-messages"]',
        'message_list_alt': '#main [role="application"]',
        'message_list_alt2': '#main .copyable-area',
        'message_list_alt3': '#main',
        'message_row': '[role="row"]',
        'message_row_alt': '[data-testid="msg-container"]',
        'message_in': '.message-in',
        'message_out': '.message-out',
        'message_text': '[data-testid="msg-text"], .selectable-text, ._ao3e',
        'message_time': '[data-testid="msg-meta"]',
        'document_thumb': '[data-testid="document-thumb"]',
        'document_thumb_alt': '[data-testid="media-url-text"]',
        'document_name': '[data-testid="document-title"]',
        'document_download': '[data-testid="media-download"]',
        'sender_name': '[data-testid="msg-header"], .copyable-text[data-pre-plain-text]',
    }
    
    # Contract keywords for classification (preliminary - by filename/message)
    # Final classification should be done by DocumentProcessor using RAG
    CONTRACT_KEYWORDS = [
        # Russian
        'договор', 'контракт', 'соглашение', 'акт',
        'счёт', 'счет', 'счёт-фактура', 'упд',
        'накладная', 'приложение к договору', 
        'дополнительное соглашение', 'доп соглашение',
        'коммерческое предложение', 'спецификация',
        # English
        'invoice', 'contract', 'agreement', 'nda',
        # Action keywords in message
        'подпиши', 'на подпись', 'согласуй', 'утверди',
    ]
    
    # Document extensions to look for
    DOCUMENT_EXTENSIONS = ['.pdf', '.docx', '.doc', '.xlsx', '.xls']
    
    def __init__(self, page: Page):
        """Initialize message scanner.
        
        Args:
            page: Playwright page with WhatsApp chat open.
        """
        self.page = page
    
    async def scan_messages(
        self,
        chat_name: str,
        limit: int = 100,
        documents_only: bool = False
    ) -> List[MessageInfo]:
        """Scan all messages in current chat.
        
        Args:
            chat_name: Name of the current chat.
            limit: Maximum messages to scan.
            documents_only: Only return messages with documents.
            
        Returns:
            List of MessageInfo objects.
        """
        messages = []
        
        try:
            # Wait for main panel to be visible (chat is open)
            await asyncio.sleep(0.5)  # Give time for chat to load
            
            # Check if chat is actually open
            has_main = await self.page.evaluate('() => !!document.querySelector("#main")')
            if not has_main:
                logger.warning(f'No #main found - chat {chat_name} not open')
                return []
            
            # ALWAYS use JavaScript method first - it's more reliable
            # because it finds documents by filename text in spans
            messages = await self._scan_messages_via_js(chat_name, documents_only)
            
            if messages:
                logger.info(f'Found {len(messages)} messages via JS in {chat_name}')
                return messages[:limit]
            
            # Fallback: try CSS selectors for message parsing
            logger.debug(f'JS found nothing, trying CSS selectors for {chat_name}')
            
            # Try multiple selectors for message list
            message_list = None
            selectors_to_try = [
                self.SELECTORS['message_list'],
                self.SELECTORS['message_list_alt'],
                self.SELECTORS['message_list_alt2'],
                self.SELECTORS['message_list_alt3'],
            ]
            
            for selector in selectors_to_try:
                try:
                    message_list = await self.page.wait_for_selector(
                        selector,
                        timeout=2000
                    )
                    if message_list:
                        logger.debug(f'Found message list with: {selector}')
                        break
                except:
                    continue
            
            if not message_list:
                return []
            
            # Get message rows - try multiple selectors
            rows = []
            row_selectors = [
                self.SELECTORS['message_row'],
                self.SELECTORS['message_row_alt'],
            ]
            
            for selector in row_selectors:
                rows = await self.page.query_selector_all(selector)
                if rows:
                    break
            
            if not rows:
                return messages
            
            for row in rows[-limit:]:  # Take last N messages
                try:
                    msg = await self._parse_message(row, chat_name)
                    if msg:
                        if documents_only and not msg.has_document:
                            continue
                        messages.append(msg)
                except Exception as e:
                    logger.debug(f'Error parsing message: {e}')
                    continue
            
            logger.info(f'Scanned {len(messages)} messages in {chat_name}')
            
        except Exception as e:
            logger.error(f'Error scanning messages: {e}')
            import traceback
            logger.debug(traceback.format_exc())
        
        return messages
    
    async def _scan_messages_via_js(
        self,
        chat_name: str,
        documents_only: bool = False
    ) -> List[MessageInfo]:
        """Scan messages using JavaScript - more reliable fallback."""
        try:
            result = await self.page.evaluate(r'''
                (documentsOnly) => {
                    const messages = [];
                    const foundDocs = new Set();  // Avoid duplicates
                    const main = document.querySelector('#main');
                    if (!main) return messages;
                    
                    // Document extensions to look for
                    const docExtensions = /\.(pdf|docx?|xlsx?|pptx?|txt|csv)$/i;
                    
                    // METHOD 1: Find spans containing file names (most reliable for new WhatsApp)
                    const allSpans = main.querySelectorAll('span');
                    allSpans.forEach((span, idx) => {
                        const text = (span.textContent || '').trim();
                        if (docExtensions.test(text) && text.length < 200) {
                            // This span contains a filename
                            const docName = text;
                            if (foundDocs.has(docName)) return;
                            foundDocs.add(docName);
                            
                            // Find parent message container
                            let container = span;
                            for (let i = 0; i < 20; i++) {
                                container = container.parentElement;
                                if (!container) break;
                                // Look for message bubble or row
                                const role = container.getAttribute('role');
                                const classes = container.className || '';
                                if (role === 'row' || 
                                    classes.includes('message-') ||
                                    container.getAttribute('data-id')) {
                                    break;
                                }
                            }
                            
                            // Get time from container
                            let timeStr = '';
                            if (container) {
                                const timeEl = container.querySelector('[data-testid="msg-meta"], span[dir="auto"]:last-child');
                                if (timeEl) {
                                    const timeText = timeEl.textContent || '';
                                    // Extract time like "15:30" or "3:45 PM"
                                    const timeMatch = timeText.match(/\d{1,2}:\d{2}(\s*[AP]M)?/i);
                                    if (timeMatch) timeStr = timeMatch[0];
                                }
                            }
                            
                            messages.push({
                                id: `doc_span_${idx}_${Date.now()}`,
                                content: '',
                                document_name: docName,
                                has_document: true,
                                time: timeStr,
                                element_tag: span.tagName,
                                method: 'span_text'
                            });
                        }
                    });
                    
                    // METHOD 2: Find traditional document-thumb elements
                    const docs = main.querySelectorAll(
                        '[data-testid="document-thumb"], ' +
                        '[data-testid="media-url-text"], ' +
                        'a[href*=".pdf"], a[href*=".doc"]'
                    );
                    
                    docs.forEach((doc, idx) => {
                        let docName = '';
                        const titleEl = doc.querySelector('[data-testid="document-title"]') ||
                                       doc.querySelector('span');
                        if (titleEl) {
                            docName = (titleEl.textContent || '').trim();
                        }
                        if (!docName) {
                            const href = doc.getAttribute('href') || '';
                            if (href) docName = href.split('/').pop() || 'document';
                        }
                        
                        if (docName && !foundDocs.has(docName)) {
                            foundDocs.add(docName);
                            
                            let container = doc;
                            for (let i = 0; i < 15; i++) {
                                container = container.parentElement;
                                if (!container) break;
                                if (container.getAttribute('role') === 'row') break;
                            }
                            
                            let timeStr = '';
                            if (container) {
                                const timeEl = container.querySelector('[data-testid="msg-meta"]');
                                if (timeEl) timeStr = timeEl.textContent || '';
                            }
                            
                            messages.push({
                                id: `doc_thumb_${idx}_${Date.now()}`,
                                content: '',
                                document_name: docName,
                                has_document: true,
                                time: timeStr,
                                method: 'document_thumb'
                            });
                        }
                    });
                    
                    // METHOD 3: Find clickable document areas (buttons with file icons)
                    const buttons = main.querySelectorAll('div[role="button"], button');
                    buttons.forEach((btn, idx) => {
                        const text = (btn.textContent || '').trim();
                        if (docExtensions.test(text) && text.length < 200) {
                            const docName = text.match(/[^\s]+\.(pdf|docx?|xlsx?)/i)?.[0];
                            if (docName && !foundDocs.has(docName)) {
                                foundDocs.add(docName);
                                messages.push({
                                    id: `doc_btn_${idx}_${Date.now()}`,
                                    content: '',
                                    document_name: docName,
                                    has_document: true,
                                    time: '',
                                    method: 'button'
                                });
                            }
                        }
                    });
                    
                    // If not documents_only, also get text messages
                    if (!documentsOnly) {
                        const textEls = main.querySelectorAll('[data-testid="msg-text"], .selectable-text, ._ao3e');
                        textEls.forEach((el, idx) => {
                            const text = (el.textContent || '').trim();
                            if (text && text.length > 10 && !docExtensions.test(text)) {
                                const isDuplicate = messages.some(m => m.content === text);
                                if (!isDuplicate) {
                                    messages.push({
                                        id: `txt_${idx}_${Date.now()}`,
                                        content: text,
                                        has_document: false,
                                        method: 'text'
                                    });
                                }
                            }
                        });
                    }
                    
                    return messages;
                }
            ''', documents_only)
            
            # Log what we found
            doc_count = sum(1 for m in result if m.get('has_document'))
            if doc_count > 0:
                logger.info(f'JS scan found {doc_count} documents in {chat_name}')
                for m in result:
                    if m.get('has_document'):
                        logger.debug(f"  - {m.get('document_name')} (method: {m.get('method', 'unknown')})")
            
            return [
                MessageInfo(
                    id=m.get('id', ''),
                    sender=chat_name,
                    content=m.get('content', ''),
                    timestamp=datetime.now(),
                    chat_name=chat_name,
                    has_document=m.get('has_document', False),
                    document_name=m.get('document_name'),
                    is_contract=self._is_contract(
                        m.get('content', ''),
                        m.get('document_name')
                    ),
                    metadata={'method': m.get('method', 'unknown')}
                )
                for m in result
            ]
            
        except Exception as e:
            logger.error(f'JS message scan failed: {e}')
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    async def _parse_message(
        self,
        element: ElementHandle,
        chat_name: str
    ) -> Optional[MessageInfo]:
        """Parse message info from DOM element.
        
        Args:
            element: Message row element.
            chat_name: Current chat name.
            
        Returns:
            MessageInfo or None.
        """
        try:
            # Get message text
            text_el = await element.query_selector(self.SELECTORS['message_text'])
            content = ''
            if text_el:
                content = await text_el.inner_text()
            
            # Get timestamp
            time_el = await element.query_selector(self.SELECTORS['message_time'])
            timestamp = datetime.now()
            if time_el:
                time_str = await time_el.inner_text()
                timestamp = self._parse_timestamp(time_str)
            
            # Get sender (for group chats)
            sender = chat_name
            sender_el = await element.query_selector(self.SELECTORS['sender_name'])
            if sender_el:
                sender_text = await sender_el.inner_text()
                if sender_text:
                    sender = sender_text.split(':')[0].strip() if ':' in sender_text else sender_text
            
            # Check if outgoing
            is_outgoing = await element.query_selector(self.SELECTORS['message_out']) is not None
            
            # Check for document
            doc_el = await element.query_selector(self.SELECTORS['document_thumb'])
            has_document = doc_el is not None
            document_name = None
            
            if has_document:
                name_el = await element.query_selector(self.SELECTORS['document_name'])
                if name_el:
                    document_name = await name_el.inner_text()
            
            # Generate unique ID
            msg_id = self._generate_id(chat_name, sender, content, timestamp)
            
            # Classify as contract
            is_contract = self._is_contract(content, document_name)
            
            return MessageInfo(
                id=msg_id,
                sender=sender,
                content=content,
                timestamp=timestamp,
                chat_name=chat_name,
                has_document=has_document,
                document_name=document_name,
                document_element=doc_el if has_document else None,
                is_contract=is_contract,
                is_outgoing=is_outgoing
            )
            
        except Exception as e:
            logger.debug(f'Parse error: {e}')
            return None
    
    def _parse_timestamp(self, time_str: str) -> datetime:
        """Parse timestamp from WhatsApp format.
        
        Args:
            time_str: Time string like "15:30" or "10:45 AM".
            
        Returns:
            datetime object (today's date with parsed time).
        """
        now = datetime.now()
        try:
            # Remove extra characters
            time_str = time_str.strip()
            
            # Try different formats
            for fmt in ['%H:%M', '%I:%M %p', '%H:%M:%S']:
                try:
                    parsed = datetime.strptime(time_str, fmt)
                    return now.replace(
                        hour=parsed.hour,
                        minute=parsed.minute,
                        second=parsed.second if hasattr(parsed, 'second') else 0
                    )
                except ValueError:
                    continue
                    
        except Exception:
            pass
        
        return now
    
    def _generate_id(
        self,
        chat_name: str,
        sender: str,
        content: str,
        timestamp: datetime
    ) -> str:
        """Generate unique message ID.
        
        Args:
            chat_name: Chat name.
            sender: Sender name.
            content: Message content.
            timestamp: Message timestamp.
            
        Returns:
            Unique ID string.
        """
        data = f'{chat_name}:{sender}:{content[:100]}:{timestamp.isoformat()}'
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def _is_contract(
        self,
        content: str,
        document_name: Optional[str]
    ) -> bool:
        """Classify message as potential contract.
        
        Args:
            content: Message text.
            document_name: Attached document name.
            
        Returns:
            True if likely a contract.
        """
        # Check content
        content_lower = (content or '').lower()
        for keyword in self.CONTRACT_KEYWORDS:
            if keyword in content_lower:
                return True
        
        # Check document name for contract keywords
        if document_name:
            doc_lower = document_name.lower()
            for keyword in self.CONTRACT_KEYWORDS:
                if keyword in doc_lower:
                    return True
        
        # Note: we do NOT classify by extension alone
        # Final classification should use DocumentProcessor with RAG
        return False
    
    async def find_documents(self, chat_name: str) -> List[MessageInfo]:
        """Find all document messages in current chat.
        
        Args:
            chat_name: Current chat name.
            
        Returns:
            List of messages with documents.
        """
        messages = await self.scan_messages(chat_name, documents_only=True)
        return messages
    
    async def find_contracts(self, chat_name: str) -> List[MessageInfo]:
        """Find all potential contract messages in current chat.
        
        Args:
            chat_name: Current chat name.
            
        Returns:
            List of messages classified as contracts.
        """
        messages = await self.scan_messages(chat_name)
        return [m for m in messages if m.is_contract]
