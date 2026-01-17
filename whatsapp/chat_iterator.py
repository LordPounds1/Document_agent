"""Chat iterator for WhatsApp Web.

Iterates through all chats in the sidebar and provides navigation.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
logger = logging.getLogger(__name__)

try:
    from playwright.async_api import Page, ElementHandle
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None  # type: ignore[assignment]
    ElementHandle = None  # type: ignore[assignment]


@dataclass
class ChatInfo:
    """Information about a WhatsApp chat."""
    name: str
    last_message: str = ''
    unread_count: int = 0
    is_group: bool = False
    element: ElementHandle | None = None


class ChatIterator:
    """Iterates through WhatsApp chats.

    Provides methods to:
    - Get list of all visible chats
    - Open specific chat by name
    - Scroll to load more chats
    - Filter chats with unread messages

    Example:
        ```python
        iterator = ChatIterator(page)

        async for chat in iterator.iter_chats():
            if chat.unread_count > 0:
                await iterator.open_chat(chat.name)
                # ... process chat
        ```
    """

    # Multiple selector variants - WhatsApp Web changes DOM frequently
    SELECTORS = {
        'chat_list': '[data-testid="chat-list"]',
        'chat_item': '[data-testid="cell-frame-container"]',
        'chat_item_alt': '[data-testid="list-item-container"]',
        'chat_item_alt2': '#pane-side > div > div > div > div',  # Fallback
        'chat_title': '[data-testid="cell-frame-title"] span',
        'chat_title_alt': 'span[title]',
        'chat_title_alt2': '[data-testid="conversation-info-header-chat-title"]',
        'last_message': '[data-testid="last-msg-status"]',
        'last_message_alt': '._ao3e',  # Class-based fallback
        'unread_badge': '[data-testid="icon-unread-count"]',
        'unread_badge_alt': 'span[aria-label*="unread"]',
        'search_box': '[data-testid="chat-list-search"]',
        'search_input': '[data-testid="chat-list-search"] input',
        'side_panel': '#side',
        'pane_side': '#pane-side',
    }

    def __init__(self, page: Page):
        """Initialize chat iterator.

        Args:
            page: Playwright page with WhatsApp Web loaded.
        """
        self.page = page

    async def get_chats(self, limit: int = 50) -> list[ChatInfo]:
        """Get list of visible chats.

        Args:
            limit: Maximum number of chats to return.

        Returns:
            List of ChatInfo objects.
        """
        chats = []

        try:
            # Wait for chat list
            await self.page.wait_for_selector(
                self.SELECTORS['pane_side'],
                timeout=10000
            )

            # Give WhatsApp time to render chats
            await asyncio.sleep(1)

            # Try multiple selectors for chat items
            chat_elements = []
            selectors_to_try = [
                self.SELECTORS['chat_item'],
                self.SELECTORS['chat_item_alt'],
                self.SELECTORS['chat_item_alt2'],
            ]

            for selector in selectors_to_try:
                chat_elements = await self.page.query_selector_all(selector)
                if chat_elements:
                    logger.debug(f'Found {len(chat_elements)} elements with selector: {selector}')
                    break

            # If still no elements, try JavaScript approach
            if not chat_elements:
                chats = await self._get_chats_via_js()
                if chats:
                    logger.info(f'Found {len(chats)} chats via JS')
                    return chats[:limit]

            for element in chat_elements[:limit]:
                try:
                    chat = await self._parse_chat_element(element)
                    if chat and chat.name:
                        chats.append(chat)
                except Exception as e:
                    logger.debug(f'Error parsing chat element: {e}')
                    continue

            logger.info(f'Found {len(chats)} chats')

        except Exception as e:
            logger.error(f'Error getting chats: {e}')

        return chats

    async def _get_chats_via_js(self) -> list[ChatInfo]:
        """Get chats using JavaScript evaluation - more reliable."""
        try:
            result = await self.page.evaluate('''
                () => {
                    const chats = [];

                    // Method 1: Find all elements with title attribute in side panel
                    const sidePanel = document.querySelector('#pane-side');
                    if (!sidePanel) return chats;

                    // Find all clickable chat rows
                    const rows = sidePanel.querySelectorAll('[role="listitem"], [role="row"], [data-testid="cell-frame-container"], [data-testid="list-item-container"]');

                    if (rows.length === 0) {
                        // Fallback: find all spans with title in side panel
                        const spans = sidePanel.querySelectorAll('span[title]');
                        spans.forEach(span => {
                            const title = span.getAttribute('title');
                            if (title && title.length > 0 && title.length < 100) {
                                chats.push({
                                    name: title,
                                    last_message: '',
                                    unread_count: 0
                                });
                            }
                        });
                    } else {
                        rows.forEach(row => {
                            // Find chat name
                            const titleSpan = row.querySelector('span[title]');
                            if (titleSpan) {
                                const name = titleSpan.getAttribute('title') || titleSpan.textContent;
                                if (name && name.trim()) {
                                    // Find last message
                                    let lastMsg = '';
                                    const msgSpan = row.querySelector('[data-testid="last-msg-status"]');
                                    if (msgSpan) lastMsg = msgSpan.textContent || '';

                                    // Find unread count
                                    let unread = 0;
                                    const unreadSpan = row.querySelector('[data-testid="icon-unread-count"]');
                                    if (unreadSpan) {
                                        const unreadText = unreadSpan.textContent;
                                        unread = parseInt(unreadText) || 0;
                                    }

                                    chats.push({
                                        name: name.trim(),
                                        last_message: lastMsg,
                                        unread_count: unread
                                    });
                                }
                            }
                        });
                    }

                    // Remove duplicates
                    const seen = new Set();
                    return chats.filter(chat => {
                        if (seen.has(chat.name)) return false;
                        seen.add(chat.name);
                        return true;
                    });
                }
            ''')

            return [
                ChatInfo(
                    name=c['name'],
                    last_message=c.get('last_message', ''),
                    unread_count=c.get('unread_count', 0)
                )
                for c in result
            ]

        except Exception as e:
            logger.error(f'JS chat extraction failed: {e}')
            return []

    async def _parse_chat_element(self, element: ElementHandle) -> ChatInfo | None:
        """Parse chat info from DOM element.

        Args:
            element: Chat item element.

        Returns:
            ChatInfo or None if parsing failed.
        """
        try:
            # Get chat name
            title_el = await element.query_selector(self.SELECTORS['chat_title'])
            if not title_el:
                title_el = await element.query_selector(self.SELECTORS['chat_title_alt'])

            name = ''
            if title_el:
                name = await title_el.inner_text()
                if not name:
                    name = await title_el.get_attribute('title') or ''

            if not name:
                return None

            # Get last message
            last_msg_el = await element.query_selector(self.SELECTORS['last_message'])
            last_message = ''
            if last_msg_el:
                last_message = await last_msg_el.inner_text()

            # Get unread count
            unread_count = 0
            unread_el = await element.query_selector(self.SELECTORS['unread_badge'])
            if unread_el:
                unread_text = await unread_el.inner_text()
                try:
                    unread_count = int(unread_text)
                except ValueError:
                    unread_count = 1  # Has unread but count not parseable

            # Detect group (usually has group icon or multiple participants in title)
            is_group = '@' in name or await element.query_selector('[data-testid="group"]') is not None

            return ChatInfo(
                name=name.strip(),
                last_message=last_message.strip(),
                unread_count=unread_count,
                is_group=is_group,
                element=element
            )

        except Exception as e:
            logger.debug(f'Error parsing chat: {e}')
            return None

    async def iter_chats(
        self,
        scroll_count: int = 5,
        scroll_delay: float = 0.5
    ) -> AsyncIterator[ChatInfo]:
        """Iterate through all chats, scrolling to load more.

        Args:
            scroll_count: Number of times to scroll down.
            scroll_delay: Delay between scrolls in seconds.

        Yields:
            ChatInfo objects for each chat.
        """
        seen_names = set()

        # Initial chats
        chats = await self.get_chats(limit=100)
        for chat in chats:
            if chat.name not in seen_names:
                seen_names.add(chat.name)
                yield chat

        # Scroll and get more
        for _ in range(scroll_count):
            await self._scroll_chat_list()
            await asyncio.sleep(scroll_delay)

            chats = await self.get_chats(limit=100)
            for chat in chats:
                if chat.name not in seen_names:
                    seen_names.add(chat.name)
                    yield chat

    async def _scroll_chat_list(self) -> None:
        """Scroll the chat list to load more chats."""
        try:
            pane = await self.page.query_selector(self.SELECTORS['pane_side'])
            if pane:
                await pane.evaluate('el => el.scrollBy(0, 500)')
        except Exception as e:
            logger.debug(f'Scroll failed: {e}')

    async def open_chat(self, chat_name: str) -> bool:
        """Open a chat by name.

        Args:
            chat_name: Name of the chat to open.

        Returns:
            True if chat was opened successfully.
        """
        if not chat_name or not chat_name.strip():
            return False

        try:
            # Method 1: Click directly in sidebar using Playwright locator
            direct_success = await self._click_chat_in_sidebar(chat_name)
            if direct_success:
                # Verify chat opened by checking #main
                await asyncio.sleep(1)
                has_main = await self.page.evaluate('() => !!document.querySelector("#main")')
                if has_main:
                    logger.debug(f'Opened chat via direct click: {chat_name}')
                    return True

            # Method 2: Use search
            search_success = await self._search_and_click(chat_name)
            if search_success:
                await asyncio.sleep(1)
                has_main = await self.page.evaluate('() => !!document.querySelector("#main")')
                if has_main:
                    logger.debug(f'Opened chat via search: {chat_name}')
                    return True

            # Method 3: Fallback - scroll through chat list and use element.click()
            async for chat in self.iter_chats(scroll_count=5):
                if chat.name.lower() == chat_name.lower() and chat.element:
                    await chat.element.click()
                    await asyncio.sleep(1)
                    has_main = await self.page.evaluate('() => !!document.querySelector("#main")')
                    if has_main:
                        return True

            logger.warning(f'Chat not found or could not open: {chat_name}')
            return False

        except Exception as e:
            logger.error(f'Error opening chat {chat_name}: {e}')
            return False

    async def _click_chat_in_sidebar(self, chat_name: str) -> bool:
        """Click on chat directly in sidebar using Playwright locators.

        Args:
            chat_name: Chat name to click.

        Returns:
            True if clicked.
        """
        try:
            # Use Playwright's locator - exact match first (most reliable)
            locator = self.page.locator(f'#pane-side span[title="{chat_name}"]')
            count = await locator.count()
            logger.debug(f'Exact match for "{chat_name}": {count}')

            if count > 0:
                await locator.first.click()
                await asyncio.sleep(0.5)
                return True

            # Try partial match
            locator = self.page.locator(f'#pane-side span[title*="{chat_name}"]')
            count = await locator.count()
            logger.debug(f'Partial match for "{chat_name}": {count}')

            if count > 0:
                await locator.first.click()
                await asyncio.sleep(0.5)
                return True

            # Try by text content
            locator = self.page.locator('#pane-side').get_by_text(chat_name, exact=False)
            count = await locator.count()

            if count > 0:
                await locator.first.click()
                await asyncio.sleep(0.5)
                return True

        except Exception as e:
            logger.debug(f'Direct sidebar click failed: {e}')

        return False

    async def _search_and_click(self, chat_name: str) -> bool:
        """Search for chat and click on result using Playwright native methods.

        Args:
            chat_name: Chat name to search for.

        Returns:
            True if found and clicked.
        """
        try:
            # Find and click search box using Playwright locator
            search_locator = self.page.locator('[data-testid="chat-list-search"]')
            if await search_locator.count() == 0:
                search_locator = self.page.locator('[contenteditable="true"]').first
            if await search_locator.count() == 0:
                search_locator = self.page.locator('div[role="textbox"]').first

            if await search_locator.count() == 0:
                logger.debug('Could not find search box')
                return False

            await search_locator.click()
            await asyncio.sleep(0.3)

            # Clear any existing text and type new search
            await self.page.keyboard.press('Control+a')
            await self.page.keyboard.type(chat_name, delay=30)
            await asyncio.sleep(1.5)  # Wait for results to load

            # Click on first matching result using Playwright locator
            # Try exact title match first
            result_locator = self.page.locator(f'span[title="{chat_name}"]')
            if await result_locator.count() > 0:
                await result_locator.first.click()
                await self._clear_search()
                return True

            # Try partial title match
            result_locator = self.page.locator(f'span[title*="{chat_name}"]')
            if await result_locator.count() > 0:
                await result_locator.first.click()
                await self._clear_search()
                return True

            # Try matching by visible text
            result_locator = self.page.get_by_text(chat_name, exact=False)
            if await result_locator.count() > 0:
                # Click the first one that's in the search results area
                await result_locator.first.click()
                await self._clear_search()
                return True

            await self._clear_search()
            return False

        except Exception as e:
            logger.debug(f'Search failed: {e}')
            await self._clear_search()

        return False

    async def _clear_search(self) -> None:
        """Clear the search box."""
        try:
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(0.2)
            await self.page.keyboard.press('Escape')
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.debug(f'Failed to close chat: {e}')

    async def scroll_chat_history(
        self,
        scroll_count: int = 20,
        scroll_delay: float = 0.3
    ) -> None:
        """Scroll up in current chat to load full history.

        Args:
            scroll_count: Number of times to scroll up.
            scroll_delay: Delay between scrolls.
        """
        try:
            # Find message container
            msg_container = await self.page.query_selector(
                '[data-testid="conversation-panel-messages"]'
            )

            if msg_container:
                for _ in range(scroll_count):
                    # Scroll up
                    await msg_container.evaluate('el => el.scrollBy(0, -1000)')
                    await asyncio.sleep(scroll_delay)

                # Scroll back to bottom
                await msg_container.evaluate('el => el.scrollTo(0, el.scrollHeight)')

                logger.info(f'Scrolled chat history {scroll_count} times')

        except Exception as e:
            logger.debug(f'Error scrolling history: {e}')
