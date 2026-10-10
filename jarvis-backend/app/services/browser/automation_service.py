import re
import time
import logging
from typing import Dict, Any, Optional, List
from app.services.browser.security import URLSecurityValidator, BrowserSecurityError
from app.services.browser.session_manager import (
    browser_session_manager,
    browser_worker,
    BrowserSession
)

logger = logging.getLogger("jarvis.browser.automation")


class BrowserAutomationError(Exception):
    """Base error for browser automation issues."""
    pass


class BrowserUnavailableError(BrowserAutomationError):
    """Browser engine cannot be launched."""
    pass


class BrowserSessionExpiredError(BrowserAutomationError):
    """Browser session not found or closed."""
    pass


class ElementNotFoundError(BrowserAutomationError):
    """Requested DOM element could not be located."""
    pass


class AmbiguousTargetError(BrowserAutomationError):
    """Multiple matching interactive elements found when a unique target was required."""
    pass


class BrowserOperationTimeoutError(BrowserAutomationError):
    """Operation timed out."""
    pass


class NoActivePageError(BrowserAutomationError):
    """No active browser session or webpage is open."""
    pass


class BrowserAutomationService:
    """
    High-level, verified browser automation service:
    Executes controlled Playwright operations inside isolated JARVIS sessions.
    """

    @staticmethod
    async def _dismiss_consent_if_present(page):
        """Dismisses common GDPR/cookie consent dialogs on Google, YouTube, etc."""
        try:
            consent_selectors = [
                'button:has-text("Accept all")',
                'button:has-text("Reject all")',
                'button:has-text("I agree")',
                'button:has-text("Stay signed out")',
                'ytd-button-renderer:has-text("Accept all") button',
                'ytd-button-renderer:has-text("Reject all") button',
                '[aria-label="Accept all"]',
                '[aria-label="Reject all"]',
                '#L2AGLb',
                '#W0wltc',
            ]
            for sel in consent_selectors:
                loc = page.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    break
        except Exception:
            pass

    def _get_active_session(self, session_id: Optional[str] = None, must_exist: bool = False) -> BrowserSession:
        sess = browser_session_manager.get_session(session_id)
        if not sess:
            if must_exist:
                raise NoActivePageError("No active browser session or webpage is currently open.")
            sess = browser_session_manager.get_or_create_session(session_id)
        if not sess or not sess.is_valid():
            if must_exist:
                raise NoActivePageError("The active browser session or webpage has been closed.")
            sess = browser_session_manager.get_or_create_session(session_id)
        return sess

    def open_session(
        self,
        session_id: Optional[str] = None,
        browser_type: Optional[str] = "msedge",
        headless: bool = False
    ) -> Dict[str, Any]:
        try:
            sess = browser_session_manager.get_or_create_session(
                session_id=session_id,
                headless=headless,
                browser_type=browser_type
            )
            return {
                "session_id": sess.session_id,
                "browser": sess.browser_type,
                "status": "READY",
                "is_closed": sess.is_closed
            }
        except Exception as e:
            logger.error(f"Failed to initialize browser session: {e}")
            raise BrowserUnavailableError(f"Could not initialize browser automation: {e}")

    def navigate(
        self,
        url: str,
        session_id: Optional[str] = None,
        timeout_ms: int = 30000,
        wait_until: str = "domcontentloaded"
    ) -> Dict[str, Any]:
        validated_url = URLSecurityValidator.validate(url)
        sess = self._get_active_session(session_id)

        async def _do_nav():
            page = sess.page
            response = await page.goto(
                validated_url,
                timeout=timeout_ms,
                wait_until=wait_until
            )
            # Validate final redirected URL
            final_url = page.url
            URLSecurityValidator.validate(final_url)

            # Dismiss cookie consent dialog if presented
            await self._dismiss_consent_if_present(page)

            title = await page.title()
            status_code = response.status if response else 200
            return final_url, title, status_code

        try:
            timeout_sec = (timeout_ms / 1000.0) + 5.0
            final_url, title, status_code = browser_worker.run_coro(_do_nav(), timeout=timeout_sec)
            return {
                "session_id": sess.session_id,
                "url": validated_url,
                "final_url": final_url,
                "title": title,
                "status_code": status_code,
                "navigation_status": "SUCCESS"
            }
        except BrowserSecurityError:
            raise
        except Exception as e:
            err_msg = str(e)
            if "Timeout" in err_msg:
                raise BrowserOperationTimeoutError(f"Navigation to '{validated_url}' timed out ({timeout_ms}ms).")
            raise BrowserAutomationError(f"Navigation failed: {err_msg}")

    def get_page_info(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        sess = self._get_active_session(session_id, must_exist=True)

        async def _get_info():
            page = sess.page
            if page is None or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active webpage has been closed.")
            title = await page.title()
            url = page.url
            ready_state = await page.evaluate("() => document.readyState")
            return title, url, ready_state

        try:
            title, url, ready_state = browser_worker.run_coro(_get_info(), timeout=10.0)
            return {
                "session_id": sess.session_id,
                "title": title,
                "url": url,
                "ready_state": ready_state,
                "verified": True
            }
        except (NoActivePageError, BrowserAutomationError):
            raise
        except Exception as e:
            raise BrowserAutomationError(f"Failed to read page information: {e}")

    def _resolve_locator(self, page, selector=None, role=None, name=None, text=None):
        """Constructs an accessible, stable Playwright locator."""
        if role:
            if name:
                return page.get_by_role(role, name=re.compile(re.escape(name), re.I))
            return page.get_by_role(role)
        if selector:
            try:
                return page.locator(selector)
            except Exception:
                return page.get_by_text(selector, exact=False)
        if name:
            # Try placeholder or label
            return page.get_by_placeholder(name).or_(page.get_by_label(name)).or_(page.get_by_text(name))
        if text:
            return page.get_by_text(text)
        raise ElementNotFoundError("No locator criteria (selector, role, name, text) was provided.")

    def find_element(
        self,
        selector: Optional[str] = None,
        role: Optional[str] = None,
        name: Optional[str] = None,
        text: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_ms: int = 10000
    ) -> Dict[str, Any]:
        sess = self._get_active_session(session_id)
        desc = selector or role or name or text or "element"

        async def _find():
            page = sess.page
            locator = self._resolve_locator(page, selector, role, name, text)
            try:
                await locator.first.wait_for(state="attached", timeout=timeout_ms)
            except Exception:
                return 0, False, False

            count = await locator.count()
            visible = await locator.first.is_visible() if count > 0 else False
            enabled = await locator.first.is_enabled() if count > 0 else False
            return count, visible, enabled

        try:
            count, visible, enabled = browser_worker.run_coro(_find(), timeout=(timeout_ms / 1000.0) + 3.0)
            if count == 0:
                raise ElementNotFoundError(f"Element matching '{desc}' not found on page.")
            return {
                "found": True,
                "count": count,
                "is_unique": (count == 1),
                "description": desc,
                "visible": visible,
                "enabled": enabled
            }
        except ElementNotFoundError:
            raise
        except Exception as e:
            raise BrowserAutomationError(f"Element discovery failed for '{desc}': {e}")

    def fill_input(
        self,
        text: str,
        selector: Optional[str] = None,
        role: Optional[str] = None,
        name: Optional[str] = None,
        session_id: Optional[str] = None,
        clear_first: bool = True,
        timeout_ms: int = 10000
    ) -> Dict[str, Any]:
        sess = self._get_active_session(session_id, must_exist=False)
        desc = selector or role or name or "input field"

        async def _fill():
            page = sess.page
            if page is None or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active webpage has been closed.")
            await self._dismiss_consent_if_present(page)
            # Smart selector resolution for common search fields if not specified
            if not selector and not role and not name:
                # Try standard search query inputs (YouTube, Google, general search)
                candidate_locators = [
                    page.locator('input[name="search_query"]'),  # YouTube
                    page.locator('input#search'),                # YouTube fallback
                    page.locator('textarea[name="q"]'),          # Google
                    page.locator('input[name="q"]'),             # Google / DuckDuckGo
                    page.get_by_role("searchbox"),
                    page.get_by_placeholder("Search", exact=False),
                    page.locator('input[type="search"]'),
                    page.locator('input[type="text"]')
                ]
                target_locator = None
                for cand in candidate_locators:
                    try:
                        if await cand.first.is_visible():
                            target_locator = cand.first
                            break
                    except Exception:
                        continue
                if not target_locator:
                    raise ElementNotFoundError("Could not auto-detect a visible search input field on this page.")
            else:
                loc = self._resolve_locator(page, selector, role, name)
                count = await loc.count()
                if count == 0:
                    raise ElementNotFoundError(f"Target input field matching '{desc}' not found.")
                target_locator = loc.first

            await target_locator.wait_for(state="visible", timeout=timeout_ms)
            if clear_first:
                await target_locator.fill("")
            await target_locator.fill(text)
            tag = await target_locator.evaluate("el => el.tagName.toLowerCase()")
            return tag

        try:
            tag = browser_worker.run_coro(_fill(), timeout=(timeout_ms / 1000.0) + 3.0)
            return {
                "filled": True,
                "target": desc,
                "text_length": len(text),
                "element_tag": tag
            }
        except (ElementNotFoundError, AmbiguousTargetError, NoActivePageError):
            raise
        except Exception as e:
            err_msg = str(e)
            if "Timeout" in err_msg:
                raise BrowserOperationTimeoutError(f"Timed out waiting to fill input '{desc}'.")
            raise BrowserAutomationError(f"Failed entering text into '{desc}': {err_msg}")

    def click_element(
        self,
        selector: Optional[str] = None,
        role: Optional[str] = None,
        name: Optional[str] = None,
        text: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_ms: int = 10000
    ) -> Dict[str, Any]:
        sess = self._get_active_session(session_id, must_exist=True)
        desc = selector or role or name or text or "element"

        async def _click():
            page = sess.page
            if page is None or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active webpage has been closed.")
            await self._dismiss_consent_if_present(page)
            loc = self._resolve_locator(page, selector, role, name, text)
            count = await loc.count()
            if count == 0:
                raise ElementNotFoundError(f"Click target matching '{desc}' was not found on page.")
            if count > 1 and not selector:
                raise AmbiguousTargetError(f"Multiple targets ({count}) matched '{desc}'. Ambiguous action rejected.")

            target = loc.first
            await target.wait_for(state="visible", timeout=timeout_ms)
            await target.click(timeout=timeout_ms)
            return page.url

        try:
            new_url = browser_worker.run_coro(_click(), timeout=(timeout_ms / 1000.0) + 3.0)
            return {
                "clicked": True,
                "target": desc,
                "new_url": new_url
            }
        except (ElementNotFoundError, AmbiguousTargetError, NoActivePageError):
            raise
        except Exception as e:
            err_msg = str(e)
            if "Timeout" in err_msg:
                raise BrowserOperationTimeoutError(f"Click operation timed out on '{desc}'.")
            raise BrowserAutomationError(f"Click failed on '{desc}': {err_msg}")

    def press_key(
        self,
        key: str,
        selector: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_ms: int = 10000
    ) -> Dict[str, Any]:
        sess = self._get_active_session(session_id, must_exist=True)

        async def _press():
            page = sess.page
            if page is None or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active webpage has been closed.")
            if selector:
                loc = page.locator(selector)
                await loc.first.press(key, timeout=timeout_ms)
            else:
                await page.keyboard.press(key)

        try:
            browser_worker.run_coro(_press(), timeout=(timeout_ms / 1000.0) + 3.0)
            return {
                "pressed": True,
                "key": key,
                "target": selector or "active_page"
            }
        except (NoActivePageError, BrowserAutomationError):
            raise
        except Exception as e:
            raise BrowserAutomationError(f"Failed pressing key '{key}': {e}")

    def get_text(
        self,
        selector: Optional[str] = None,
        max_chars: int = 2000,
        session_id: Optional[str] = None,
        timeout_ms: int = 10000
    ) -> Dict[str, Any]:
        sess = self._get_active_session(session_id, must_exist=True)

        async def _read():
            page = sess.page
            if page is None or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active webpage has been closed.")
            if selector:
                loc = page.locator(selector)
                txt = await loc.first.inner_text(timeout=timeout_ms)
            else:
                txt = await page.inner_text("body", timeout=timeout_ms)
            return txt

        try:
            raw_text = browser_worker.run_coro(_read(), timeout=(timeout_ms / 1000.0) + 3.0)
            clean_text = raw_text.strip()[:max_chars]
            return {
                "text": clean_text,
                "char_count": len(clean_text),
                "truncated": len(raw_text.strip()) > max_chars
            }
        except (NoActivePageError, BrowserAutomationError):
            raise
        except Exception as e:
            raise BrowserAutomationError(f"Failed retrieving text: {e}")

    def wait_for_state(
        self,
        state: Optional[str] = "networkidle",
        selector: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_ms: int = 15000
    ) -> Dict[str, Any]:
        sess = self._get_active_session(session_id, must_exist=True)

        async def _wait():
            page = sess.page
            if page is None or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active webpage has been closed.")
            if selector:
                loc = page.locator(selector)
                try:
                    await loc.first.wait_for(state="visible", timeout=timeout_ms)
                except Exception:
                    # Also try domcontentloaded and count check
                    await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                    if await loc.count() > 0:
                        return selector
                    raise
                return selector
            else:
                st = state if state in ["networkidle", "domcontentloaded", "load"] else "domcontentloaded"
                await page.wait_for_load_state(st, timeout=timeout_ms)
                return st

        try:
            condition = browser_worker.run_coro(_wait(), timeout=(timeout_ms / 1000.0) + 3.0)
            return {
                "waited_for": condition,
                "satisfied": True,
                "found_selector": selector
            }
        except (NoActivePageError, BrowserOperationTimeoutError, BrowserAutomationError):
            raise
        except Exception as e:
            err_msg = str(e)
            if "Timeout" in err_msg:
                raise BrowserOperationTimeoutError(f"Wait condition '{selector or state}' timed out ({timeout_ms}ms).")
            raise BrowserAutomationError(f"Wait for state failed: {err_msg}")

    def close(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        closed = browser_session_manager.close_session(session_id)
        return {
            "session_id": session_id or "default",
            "closed": closed,
            "message": "Browser session closed successfully." if closed else "Session was already closed."
        }


browser_automation_service = BrowserAutomationService()
