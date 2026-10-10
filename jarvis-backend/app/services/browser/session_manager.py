import os
import time
import uuid
import shutil
import asyncio
import logging
import threading
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from app.services.browser.security import URLSecurityValidator, BlockedDestinationError, UnsupportedSchemeError

logger = logging.getLogger("jarvis.browser.session")

MAX_CONCURRENT_SESSIONS = 3
IDLE_SESSION_TIMEOUT_SEC = 900  # 15 minutes


class BrowserSession:
    """Represents an isolated, JARVIS-controlled browser context and page."""

    def __init__(
        self,
        session_id: str,
        context: Any,
        page: Any,
        isolated_dir: Path,
        browser_type: str = "msedge"
    ):
        self.session_id = session_id
        self.context = context
        self.page = page
        self.isolated_dir = isolated_dir
        self.browser_type = browser_type
        self.created_at = time.time()
        self.last_active_at = time.time()
        self.is_closed = False

    def touch(self):
        self.last_active_at = time.time()


class BrowserWorkerLoop:
    """
    Dedicated worker thread running an independent asyncio event loop
    specifically for Playwright operations. Prevents event loop conflicts
    with FastAPI / Uvicorn and ensures thread safety.
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name="JARVIS-BrowserWorker", daemon=True)
        self.thread.start()
        self.playwright = None
        self._is_started = False
        self._lock = threading.Lock()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_coro(self, coro, timeout: float = 30.0):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def ensure_started(self):
        with self._lock:
            if not self._is_started:
                async def _init_pw():
                    from playwright.async_api import async_playwright
                    self.playwright = await async_playwright().start()

                self.run_coro(_init_pw(), timeout=15.0)
                self._is_started = True

    def stop(self):
        with self._lock:
            if self._is_started and self.playwright:
                async def _stop_pw():
                    await self.playwright.stop()

                try:
                    self.run_coro(_stop_pw(), timeout=10.0)
                except Exception as e:
                    logger.warning(f"Error stopping Playwright instance: {e}")
                self._is_started = False


# Global dedicated browser loop
browser_worker = BrowserWorkerLoop()


class BrowserSessionManager:
    """
    Manages JARVIS browser sessions:
    - Creates isolated browser contexts with dedicated user data directories
    - Enforces navigation route interception for SSRF / redirect protection
    - Manages timeouts, lifecycle, and safe cleanup
    - Protects user's personal browser profiles
    """

    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
        self._active_session_id: Optional[str] = None
        self._lock = threading.Lock()
        self.base_profile_dir = Path(tempfile.gettempdir()) / "jarvis_browser_profiles"
        self.base_profile_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_browser_channel(self, requested: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Resolves preferred browser channel (msedge or chrome) without runtime downloads."""
        preferred = (requested or "").lower()
        if preferred in ["chrome", "google chrome"]:
            # Check Chrome binary
            chrome_path = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
            if chrome_path.exists():
                return "chromium", "chrome"
        elif preferred in ["msedge", "edge", "microsoft edge"]:
            edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
            if edge_path.exists():
                return "chromium", "msedge"

        # Default detection: Edge first on Windows, then Chrome
        edge_path = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        if edge_path.exists():
            return "chromium", "msedge"
        chrome_path = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if chrome_path.exists():
            return "chromium", "chrome"

        return "chromium", None

    def get_session(self, session_id: Optional[str] = None) -> Optional[BrowserSession]:
        with self._lock:
            target_id = session_id or self._active_session_id
            if target_id and target_id in self._sessions:
                sess = self._sessions[target_id]
                if not sess.is_closed:
                    sess.touch()
                    return sess
            return None

    def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        headless: bool = False,
        browser_type: Optional[str] = "msedge"
    ) -> BrowserSession:
        with self._lock:
            # 1. Reuse existing session if valid
            target_id = session_id or self._active_session_id
            if target_id and target_id in self._sessions:
                sess = self._sessions[target_id]
                if not sess.is_closed:
                    sess.touch()
                    return sess

            # 2. Cleanup idle sessions if at max limit
            self._cleanup_idle_sessions()
            if len(self._sessions) >= MAX_CONCURRENT_SESSIONS:
                oldest_id = min(self._sessions.keys(), key=lambda k: self._sessions[k].last_active_at)
                self._close_session_locked(oldest_id)

            # 3. Create fresh session
            new_id = session_id or f"sess_{uuid.uuid4().hex[:10]}"
            session = self._create_session_internal(new_id, headless=headless, browser_type=browser_type)
            self._sessions[new_id] = session
            self._active_session_id = new_id
            return session

    def _create_session_internal(
        self,
        session_id: str,
        headless: bool,
        browser_type: Optional[str]
    ) -> BrowserSession:
        browser_worker.ensure_started()
        profile_dir = self.base_profile_dir / session_id
        profile_dir.mkdir(parents=True, exist_ok=True)

        browser_family, channel = self._resolve_browser_channel(browser_type)

        async def _launch_browser():
            p = browser_worker.playwright
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check"
            ]

            context_kwargs = {
                "user_data_dir": str(profile_dir),
                "headless": headless,
                "args": launch_args,
                "viewport": {"width": 1280, "height": 800},
                "accept_downloads": False,
            }
            if channel:
                context_kwargs["channel"] = channel

            try:
                context = await p.chromium.launch_persistent_context(**context_kwargs)
            except Exception as e:
                # Fallback to standard launch if persistent context fails
                logger.warning(f"Persistent context launch failed: {e}. Trying standard launch.")
                if channel:
                    browser = await p.chromium.launch(channel=channel, headless=headless, args=launch_args)
                else:
                    browser = await p.chromium.launch(headless=headless, args=launch_args)
                context = await browser.new_context(viewport={"width": 1280, "height": 800})

            # Setup route interception for SSRF / redirect protection
            async def _intercept_route(route):
                req = route.request
                if req.is_navigation_request():
                    try:
                        URLSecurityValidator.validate(req.url)
                        await route.continue_()
                    except Exception as sec_err:
                        logger.warning(f"Blocked navigation to unsafe destination '{req.url}': {sec_err}")
                        await route.abort("blockedbyclient")
                else:
                    await route.continue_()

            await context.route("**/*", _intercept_route)

            pages = context.pages
            page = pages[0] if pages else await context.new_page()
            return context, page

        context, page = browser_worker.run_coro(_launch_browser(), timeout=20.0)
        session = BrowserSession(
            session_id=session_id,
            context=context,
            page=page,
            isolated_dir=profile_dir,
            browser_type=channel or "chromium"
        )
        logger.info(f"Initialized isolated JARVIS browser session '{session_id}' using {channel or 'chromium'}.")
        return session

    def close_session(self, session_id: Optional[str] = None) -> bool:
        with self._lock:
            target_id = session_id or self._active_session_id
            if not target_id or target_id not in self._sessions:
                return False
            return self._close_session_locked(target_id)

    def _close_session_locked(self, session_id: str) -> bool:
        sess = self._sessions.pop(session_id, None)
        if not sess:
            return False

        if self._active_session_id == session_id:
            self._active_session_id = next(iter(self._sessions.keys()), None)

        sess.is_closed = True

        async def _close():
            try:
                if sess.page:
                    await sess.page.close()
            except Exception:
                pass
            try:
                if sess.context:
                    await sess.context.close()
            except Exception:
                pass

        try:
            browser_worker.run_coro(_close(), timeout=10.0)
        except Exception as e:
            logger.warning(f"Error during browser session closure for {session_id}: {e}")

        # Clean isolated profile data directory
        try:
            if sess.isolated_dir and sess.isolated_dir.exists():
                shutil.rmtree(sess.isolated_dir, ignore_errors=True)
        except Exception:
            pass

        logger.info(f"Browser session '{session_id}' closed and resources purged.")
        return True

    def _cleanup_idle_sessions(self):
        now = time.time()
        idle_ids = [
            sid for sid, s in self._sessions.items()
            if (now - s.last_active_at) > IDLE_SESSION_TIMEOUT_SEC
        ]
        for sid in idle_ids:
            logger.info(f"Purging idle browser session '{sid}'.")
            self._close_session_locked(sid)

    def close_all(self):
        with self._lock:
            for sid in list(self._sessions.keys()):
                self._close_session_locked(sid)


browser_session_manager = BrowserSessionManager()
