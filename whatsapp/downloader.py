"""Document downloader for WhatsApp Web.

Downloads documents (PDF, DOCX) from WhatsApp messages.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from whatsapp.message_scanner import MessageInfo

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Page, Download, ElementHandle
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None


class DocumentDownloader:
    """Downloads documents from WhatsApp messages.
    
    Handles:
    - Clicking download buttons
    - Waiting for download completion
    - Saving files to specified directory
    - Sanitizing filenames
    
    Example:
        ```python
        downloader = DocumentDownloader(page, downloads_dir='./downloads')
        
        for message in document_messages:
            path = await downloader.download(message)
            if path:
                print(f'Downloaded: {path}')
        ```
    """
    
    SELECTORS = {
        'document_thumb': '[data-testid="document-thumb"]',
        'download_button': '[data-testid="media-download"], [data-testid="download"]',
        'document_preview': '[data-testid="media-viewer"]',
        'close_preview': '[data-testid="media-viewer-close"]',
    }
    
    def __init__(
        self,
        page: Page,
        downloads_dir: str = 'whatsapp_downloads',
        timeout: int = 30000
    ):
        """Initialize downloader.
        
        Args:
            page: Playwright page.
            downloads_dir: Directory to save downloaded files.
            timeout: Download timeout in milliseconds.
        """
        self.page = page
        self.downloads_dir = Path(downloads_dir).absolute()
        self.timeout = timeout
        
        # Create directory
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
    
    async def download(self, message: MessageInfo) -> Optional[str]:
        """Download document from message.
        
        Args:
            message: MessageInfo with document element or document_name.
            
        Returns:
            Path to downloaded file or None if failed.
        """
        if not message.has_document:
            logger.warning('Message has no document')
            return None
        
        try:
            # If we have document_element, use it directly
            if message.document_element:
                await message.document_element.click()
                await asyncio.sleep(0.5)
            else:
                # Find document by filename text using Playwright locator
                doc_name = message.document_name
                if not doc_name:
                    logger.warning('No document name to search for')
                    return None
                
                logger.debug(f'Searching for document by name: {doc_name}')
                
                # Try to find and click the document element by text
                clicked = await self._find_and_click_document(doc_name)
                if not clicked:
                    logger.warning(f'Could not find document element for: {doc_name}')
                    return None
                
                await asyncio.sleep(0.5)
            
            # Find download button
            download_btn = await self.page.query_selector(self.SELECTORS['download_button'])
            
            if not download_btn and message.document_element:
                # Try within the document element
                download_btn = await message.document_element.query_selector(
                    self.SELECTORS['download_button']
                )
            
            if not download_btn:
                # Try clicking on the document name span directly - might trigger download
                logger.debug('No download button, trying direct click on document')
                return await self._download_via_click(message.document_name)
            
            # Start download
            async with self.page.expect_download(timeout=self.timeout) as download_info:
                await download_btn.click()
            
            download = await download_info.value
            
            # Get safe filename
            filename = self._sanitize_filename(
                message.document_name or download.suggested_filename
            )
            
            # Save file
            save_path = self.downloads_dir / filename
            await download.save_as(str(save_path))
            
            logger.info(f'Downloaded: {filename}')
            
            # Close preview if open
            await self._close_preview()
            
            return str(save_path)
            
        except Exception as e:
            logger.error(f'Download failed: {e}')
            await self._close_preview()
            return None
    
    async def download_all(
        self,
        messages: List[MessageInfo]
    ) -> List[Tuple[MessageInfo, str]]:
        """Download documents from multiple messages.
        
        Args:
            messages: List of messages with documents.
            
        Returns:
            List of (message, file_path) tuples for successful downloads.
        """
        results = []
        
        for msg in messages:
            if msg.has_document:
                path = await self.download(msg)
                if path:
                    results.append((msg, path))
                await asyncio.sleep(0.5)  # Rate limiting
        
        logger.info(f'Downloaded {len(results)} of {len(messages)} documents')
        return results
    
    def _sanitize_filename(self, filename: str) -> str:
        """Make filename safe for filesystem.
        
        Args:
            filename: Original filename.
            
        Returns:
            Sanitized filename.
        """
        if not filename:
            return f'document_{asyncio.get_event_loop().time():.0f}'
        
        # Remove path components
        filename = Path(filename).name
        
        # Remove dangerous characters
        dangerous = ['..', '/', '\\', '\x00', ':', '*', '?', '"', '<', '>', '|']
        for char in dangerous:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 200:
            name_parts = filename.rsplit('.', 1)
            if len(name_parts) == 2:
                name, ext = name_parts
                filename = name[:190] + '.' + ext
            else:
                filename = filename[:200]
        
        return filename or 'unnamed_document'
    
    async def _close_preview(self) -> None:
        """Close document preview if open."""
        try:
            close_btn = await self.page.query_selector(self.SELECTORS['close_preview'])
            if close_btn:
                await close_btn.click()
                await asyncio.sleep(0.3)
        except Exception:
            # Try pressing Escape as fallback
            try:
                await self.page.keyboard.press('Escape')
            except Exception:
                pass
    
    async def _find_and_click_document(self, doc_name: str) -> bool:
        """Find document by name and click on it.
        
        Args:
            doc_name: Document filename to search for.
            
        Returns:
            True if found and clicked.
        """
        try:
            # Try using Playwright locator to find span with document name
            locator = self.page.locator(f'#main span:text("{doc_name}")')
            if await locator.count() > 0:
                await locator.first.click()
                return True
            
            # Try partial match
            locator = self.page.locator('#main').get_by_text(doc_name, exact=False)
            if await locator.count() > 0:
                await locator.first.click()
                return True
            
            # Try finding via JavaScript and clicking
            clicked = await self.page.evaluate(r'''
                (docName) => {
                    const main = document.querySelector('#main');
                    if (!main) return false;
                    
                    // Find span containing the document name
                    const spans = main.querySelectorAll('span');
                    for (const span of spans) {
                        if (span.textContent && span.textContent.trim() === docName) {
                            // Find clickable parent (document container)
                            let el = span;
                            for (let i = 0; i < 10; i++) {
                                el = el.parentElement;
                                if (!el) break;
                                
                                // Check if this looks like a document container
                                if (el.getAttribute('role') === 'button' ||
                                    el.getAttribute('data-testid')?.includes('document') ||
                                    el.onclick) {
                                    el.click();
                                    return true;
                                }
                            }
                            // Click the span itself
                            span.click();
                            return true;
                        }
                    }
                    return false;
                }
            ''', doc_name)
            
            return clicked
            
        except Exception as e:
            logger.debug(f'Find and click document failed: {e}')
            return False
    
    async def _download_via_click(self, doc_name: str) -> Optional[str]:
        """Try to download by clicking on document name.
        
        Some WhatsApp versions allow direct download by clicking on document.
        
        Args:
            doc_name: Document filename.
            
        Returns:
            Path to downloaded file or None.
        """
        try:
            # Find the document element
            locator = self.page.locator('#main').get_by_text(doc_name, exact=False)
            if await locator.count() == 0:
                return None
            
            # Try to initiate download by clicking
            try:
                async with self.page.expect_download(timeout=5000) as download_info:
                    await locator.first.click()
                
                download = await download_info.value
                filename = self._sanitize_filename(doc_name or download.suggested_filename)
                save_path = self.downloads_dir / filename
                await download.save_as(str(save_path))
                
                logger.info(f'Downloaded via click: {filename}')
                return str(save_path)
                
            except Exception:
                # Download didn't start from click - might need to find download button
                pass
            
            # Look for download icon near the document
            download_btn = self.page.locator('#main [data-testid*="download"]')
            if await download_btn.count() > 0:
                async with self.page.expect_download(timeout=self.timeout) as download_info:
                    await download_btn.first.click()
                
                download = await download_info.value
                filename = self._sanitize_filename(doc_name or download.suggested_filename)
                save_path = self.downloads_dir / filename
                await download.save_as(str(save_path))
                
                logger.info(f'Downloaded via button: {filename}')
                return str(save_path)
            
        except Exception as e:
            logger.debug(f'Download via click failed: {e}')
        
        return None
