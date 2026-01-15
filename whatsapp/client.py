"""WhatsApp Web client using Playwright.

Handles browser launch, session persistence, and QR code authentication.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check Playwright availability
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning('Playwright not installed. Run: pip install playwright && playwright install chromium')


class WhatsAppClient:
    """WhatsApp Web client with Playwright automation.
    
    Handles:
    - Browser launch with persistent session
    - QR code authentication
    - Connection state management
    - Graceful shutdown
    
    Example:
        ```python
        async with WhatsAppClient() as client:
            if await client.wait_for_login(timeout=60):
                page = client.page
                # ... automation code
        ```
    """
    
    WHATSAPP_URL = 'https://web.whatsapp.com'
    
    # Selectors for WhatsApp Web elements
    SELECTORS = {
        'qr_canvas': 'canvas[aria-label*="QR"]',
        'qr_alt': '[data-testid="qrcode"]',
        'chat_list': '[data-testid="chat-list"]',
        'side_panel': '#side',
        'main_panel': '#main',
        'search_box': '[data-testid="chat-list-search"]',
        'loading': '[data-testid="intro-title"]',
    }
    
    def __init__(
        self,
        session_dir: str = '.whatsapp_session_playwright',
        downloads_dir: str = 'whatsapp_downloads',
        headless: bool = False,
        slow_mo: int = 50
    ):
        """Initialize WhatsApp client.
        
        Args:
            session_dir: Directory for browser session persistence.
            downloads_dir: Directory for downloaded files.
            headless: Run browser without UI (not recommended for first login).
            slow_mo: Slowdown in ms for debugging (0 for production).
        """
        self.session_dir = Path(session_dir).absolute()
        self.downloads_dir = Path(downloads_dir).absolute()
        self.headless = headless
        self.slow_mo = slow_mo
        
        # Create directories
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        
        # State
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._connected = False
    
    @property
    def page(self) -> Optional[Page]:
        """Get the browser page."""
        return self._page
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to WhatsApp."""
        return self._connected
    
    async def start(self) -> bool:
        """Start browser and navigate to WhatsApp Web.
        
        Returns:
            True if browser started successfully.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error('Playwright not available. Install: pip install playwright')
            return False
        
        try:
            self._playwright = await async_playwright().start()
            
            # Launch browser with persistent context for session
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-notifications',
                    '--no-sandbox',
                ],
                viewport={'width': 1280, 'height': 900},
                accept_downloads=True,
            )
            
            # Configure downloads
            self._context.set_default_timeout(30000)
            
            # Get or create page
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()
            
            # Navigate to WhatsApp
            logger.info('Navigating to WhatsApp Web...')
            await self._page.goto(self.WHATSAPP_URL, wait_until='networkidle')
            
            logger.info('Browser started. Check for QR code if first login.')
            return True
            
        except Exception as e:
            logger.error(f'Failed to start browser: {e}')
            await self.stop()
            return False
    
    async def wait_for_login(self, timeout: int = 120) -> bool:
        """Wait for user to scan QR code and login.
        
        Args:
            timeout: Maximum seconds to wait for login.
            
        Returns:
            True if logged in successfully.
        """
        if not self._page:
            logger.error('Browser not started')
            return False
        
        logger.info(f'Waiting for WhatsApp login (timeout: {timeout}s)...')
        logger.info('If QR code appears, scan it with WhatsApp on your phone.')
        
        try:
            # Wait for chat list to appear (indicates successful login)
            chat_list = await self._page.wait_for_selector(
                f'{self.SELECTORS["chat_list"]}, {self.SELECTORS["side_panel"]}',
                timeout=timeout * 1000,
                state='visible'
            )
            
            if chat_list:
                self._connected = True
                logger.info('Successfully logged into WhatsApp Web!')
                return True
            
        except Exception as e:
            logger.warning(f'Login wait failed: {e}')
        
        return False
    
    async def is_logged_in(self) -> bool:
        """Check if currently logged into WhatsApp.
        
        Returns:
            True if logged in.
        """
        if not self._page:
            return False
        
        try:
            chat_list = await self._page.query_selector(self.SELECTORS['chat_list'])
            side_panel = await self._page.query_selector(self.SELECTORS['side_panel'])
            return bool(chat_list or side_panel)
        except Exception:
            return False
    
    async def stop(self) -> None:
        """Stop browser and cleanup resources."""
        self._connected = False
        
        try:
            if self._context:
                await self._context.close()
                self._context = None
                self._page = None
        except Exception as e:
            logger.warning(f'Error closing context: {e}')
        
        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.warning(f'Error stopping playwright: {e}')
        
        logger.info('WhatsApp client stopped')
    
    async def screenshot(self, path: str = 'whatsapp_screenshot.png') -> None:
        """Take a screenshot for debugging.
        
        Args:
            path: Output file path.
        """
        if self._page:
            await self._page.screenshot(path=path)
            logger.info(f'Screenshot saved: {path}')
    
    async def __aenter__(self) -> 'WhatsAppClient':
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
