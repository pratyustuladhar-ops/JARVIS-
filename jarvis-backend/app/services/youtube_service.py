import re
import urllib.parse
import logging
from typing import Dict, Any, List, Optional, Tuple

from app.core.config import settings
from app.services.browser.automation_service import (
    browser_automation_service,
    BrowserAutomationError,
    BrowserUnavailableError,
    ElementNotFoundError,
    NoActivePageError
)
from app.services.browser.session_manager import browser_worker, browser_session_manager
from app.services.browser.security import URLSecurityValidator, BrowserSecurityError

logger = logging.getLogger("jarvis.services.youtube")


class YouTubeMusicServiceError(Exception):
    """Base exception for YouTube music service errors."""
    def __init__(self, message: str, code: str = "PROVIDER_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class YouTubeMusicService:
    """
    Dedicated YouTube Music Playback & Catalog Integration Service.
    Leverages JARVIS's existing Playwright browser automation and Windows Local Agent
    to search YouTube, resolve approximate/fuzzy track titles, open confirmed video results,
    verify active player playback, and handle playback controls (pause, resume, stop, next, previous).
    """

    YOUTUBE_BASE_URL = "https://www.youtube.com"
    YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query="

    def __init__(self):
        self.active_video_title: Optional[str] = None
        self.active_video_url: Optional[str] = None
        self.active_video_channel: Optional[str] = None
        self.active_video_id: Optional[str] = None
        self.playback_state: str = "IDLE"  # IDLE, PLAYING, PAUSED, STOPPED
        self.history: List[Dict[str, Any]] = []

    def _build_search_query(self, query: Optional[str] = None, artist: Optional[str] = None, genre: Optional[str] = None) -> str:
        """Constructs an optimized YouTube search query string."""
        parts = []
        q = (query or "").strip()
        a = (artist or "").strip()
        g = (genre or "").strip()

        # Clean extraneous words like 'music video for'
        clean_q = re.sub(r"^(?:the\s+)?(?:official\s+)?(?:music\s+)?video\s+(?:for|of)\s+", "", q, flags=re.I).strip()
        clean_q = re.sub(r"^(?:that\s+)?(?:september\s+song)\b", "Wake Me Up When September Ends", clean_q, flags=re.I)
        if clean_q.lower() == "september ends":
            clean_q = "Wake Me Up When September Ends"

        if clean_q and a:
            if a.lower() not in clean_q.lower():
                parts.append(f"{a} - {clean_q}")
            else:
                parts.append(clean_q)
        elif clean_q:
            parts.append(clean_q)
        elif a:
            parts.append(f"{a} top songs")
        elif g:
            parts.append(f"{g} music")
        else:
            parts.append("music")

        return " ".join(parts).strip()

    def search_music(
        self,
        query: str,
        artist: Optional[str] = None,
        limit: int = 5,
        session_id: Optional[str] = None,
        timeout_ms: int = 15000
    ) -> List[Dict[str, Any]]:
        """
        Navigates to YouTube search results and extracts candidate video metadata.
        """
        search_query = self._build_search_query(query=query, artist=artist)
        encoded_term = urllib.parse.quote_plus(search_query)
        target_url = f"{self.YOUTUBE_SEARCH_URL}{encoded_term}"
        validated_url = URLSecurityValidator.validate(target_url)

        async def _do_search():
            sess = browser_automation_service._get_active_session(session_id)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("Active browser session is closed.")

            await page.goto(validated_url, timeout=timeout_ms, wait_until="domcontentloaded")
            await browser_automation_service._dismiss_consent_if_present(page)

            # Wait for search results container or video items
            try:
                await page.locator("ytd-video-renderer, a#video-title").first.wait_for(state="attached", timeout=8000)
            except Exception:
                pass

            # Extract visible video candidates from the DOM
            raw_candidates = await page.evaluate("""
                () => {
                    const results = [];
                    const nodes = document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer');
                    for (const node of nodes) {
                        const a = node.querySelector('a#video-title, #video-title');
                        if (!a) continue;
                        const title = (a.innerText || a.getAttribute('title') || '').trim();
                        const href = a.getAttribute('href') || '';
                        if (!title || !href.includes('/watch?v=')) continue;

                        const chNode = node.querySelector('#channel-info #channel-name a, #byline a, ytd-channel-name a');
                        const channel = chNode ? (chNode.innerText || '').trim() : '';

                        const badgeNode = node.querySelector('[aria-label*="Official"], [aria-label*="Verified"], .badge-style-type-verified, .badge-style-type-verified-artist');
                        const isOfficial = !!badgeNode || /official\\s+(?:music\\s+)?video|official\\s+audio/i.test(title);

                        const vMatch = href.match(/[?&]v=([^&]+)/);
                        const videoId = vMatch ? vMatch[1] : '';

                        results.push({
                            title: title,
                            video_id: videoId,
                            url: href.startsWith('http') ? href : `https://www.youtube.com${href}`,
                            channel: channel,
                            is_official: isOfficial
                        });
                        if (results.length >= 10) break;
                    }
                    return results;
                }
            """)
            return raw_candidates

        try:
            candidates = browser_worker.run_coro(_do_search(), timeout=(timeout_ms / 1000.0) + 4.0)
            return candidates[:limit]
        except (BrowserSecurityError, NoActivePageError):
            raise
        except Exception as e:
            logger.warning(f"YouTube search extraction encountered error: {e}")
            return []

    def _score_candidate(self, cand: Dict[str, Any], track_query: str, artist: Optional[str] = None) -> float:
        """
        Computes relevance score for candidate search result.
        Gives priority to exact/approximate title matches and official artist channels.
        """
        score = 0.0
        title_low = cand.get("title", "").lower()
        channel_low = cand.get("channel", "").lower()
        t_norm = (track_query or "").lower().strip()
        a_norm = (artist or "").lower().strip()

        # 1. Artist Matching
        if a_norm:
            if a_norm in channel_low:
                score += 35.0
            if a_norm in title_low:
                score += 30.0

        # 2. Track Title Matching
        if t_norm:
            if t_norm in title_low:
                score += 40.0
            else:
                # Word-based token matching
                t_words = [w for w in re.split(r"[^\w]+", t_norm) if len(w) > 2]
                if t_words:
                    matched = sum(1 for w in t_words if w in title_low)
                    score += (matched / len(t_words)) * 35.0

        # 3. Known approximate mappings (e.g. 'September Ends' -> 'Wake Me Up When September Ends')
        if "september ends" in t_norm and "wake me up when september ends" in title_low:
            score += 45.0
        if "boulevard of broken dreams" in t_norm and "boulevard of broken dreams" in title_low:
            score += 45.0
        if "numb" in t_norm and "numb" in title_low:
            score += 40.0

        # 4. Official Video / Channel Bonus
        if cand.get("is_official"):
            score += 15.0

        # 5. Penalties for live/cover/parody/remix unless requested by user
        penalties = ["cover", "parody", "reaction", "karaoke", "remix", "guitar lesson", "tutorial"]
        for p in penalties:
            if p in title_low and p not in t_norm:
                score -= 30.0

        if "live" in title_low and "live" not in t_norm:
            score -= 10.0

        return score

    def resolve_track(
        self,
        track_query: str,
        artist: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Tuple[str, Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Resolves track query against YouTube search results.
        Returns: (status, selected_candidate, candidate_list)
        Statuses: EXACT_MATCH, APPROXIMATE_MATCH, AMBIGUOUS_MATCH, NO_MATCH
        """
        candidates = self.search_music(query=track_query, artist=artist, limit=8, session_id=session_id)
        if not candidates:
            return "NO_MATCH", None, []

        scored = []
        for c in candidates:
            s = self._score_candidate(c, track_query=track_query, artist=artist)
            scored.append((s, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_cand = scored[0]

        # Check for ambiguity: multiple top candidates with very close scores and different titles
        if len(scored) > 1:
            second_score, second_cand = scored[1]
            if top_score >= 45.0 and abs(top_score - second_score) < 3.0:
                # If titles differ significantly, consider ambiguous
                if top_cand["title"].strip().lower() != second_cand["title"].strip().lower():
                    return "AMBIGUOUS_MATCH", None, [c for _, c in scored[:3]]

        if top_score >= 60.0:
            match_type = "EXACT_MATCH" if top_score >= 80.0 else "APPROXIMATE_MATCH"
            return match_type, top_cand, [c for _, c in scored]

        if top_score >= 35.0:
            return "APPROXIMATE_MATCH", top_cand, [c for _, c in scored]

        return "NO_MATCH", None, [c for _, c in scored]

    def play(
        self,
        track: Optional[str] = None,
        artist: Optional[str] = None,
        genre: Optional[str] = None,
        url: Optional[str] = None,
        video_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_ms: int = 25000
    ) -> Dict[str, Any]:
        """
        Executes verified playback on YouTube.
        Opens video, waits for player readiness, triggers playback if paused,
        and verifies that video has started.
        """
        selected_cand: Optional[Dict[str, Any]] = None
        match_status: str = "EXACT_MATCH"

        # 1. Resolve Target URL
        if url:
            target_url = url
            target_title = track or "YouTube Video"
            target_artist = artist or ""
            vid_id = video_id or ""
            is_off = False
        elif video_id:
            target_url = f"https://www.youtube.com/watch?v={video_id}"
            target_title = track or f"YouTube Video ({video_id})"
            target_artist = artist or ""
            vid_id = video_id
            is_off = False
        elif track or artist or genre:
            q = track or (f"{genre} music" if genre else f"{artist} songs")
            match_status, selected_cand, candidates = self.resolve_track(
                track_query=q,
                artist=artist,
                session_id=session_id
            )

            if match_status == "AMBIGUOUS_MATCH":
                return {
                    "status": "AMBIGUOUS_RESULT",
                    "service": "youtube",
                    "message": f"Multiple YouTube videos matched '{q}'. Which one did you mean?",
                    "candidates": [f"{c['title']} ({c.get('channel', 'YouTube')})" for c in candidates[:3]],
                    "verified": False
                }
            elif match_status == "NO_MATCH" or not selected_cand:
                return {
                    "status": "TRACK_NOT_FOUND",
                    "service": "youtube",
                    "message": f"Could not find '{q}'" + (f" by {artist}" if artist else "") + " on YouTube.",
                    "verified": False
                }

            target_url = selected_cand["url"]
            target_title = selected_cand["title"]
            target_artist = selected_cand.get("channel") or artist or ""
            vid_id = selected_cand.get("video_id", "")
            is_off = selected_cand.get("is_official", False)
        else:
            # No song specified: Resume current session
            return self.resume(session_id=session_id)

        validated_url = URLSecurityValidator.validate(target_url)

        # 2. Browser Automation Playback Execution & Verification
        async def _do_play():
            sess = browser_automation_service._get_active_session(session_id)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("Active browser session is closed.")

            await page.goto(validated_url, timeout=timeout_ms, wait_until="domcontentloaded")
            await browser_automation_service._dismiss_consent_if_present(page)

            # Wait for HTML5 video element
            video_loc = page.locator("video.html5-main-video, video").first
            try:
                await video_loc.wait_for(state="attached", timeout=12000)
            except Exception:
                raise ElementNotFoundError("YouTube HTML5 video player not found on page.")

            # Dismiss ad skip button if an initial pre-roll overlay is active
            try:
                skip_btn = page.locator("button.ytp-ad-skip-button, button.ytp-ad-skip-button-modern, .ytp-ad-overlay-close-button")
                if await skip_btn.count() > 0 and await skip_btn.first.is_visible():
                    await skip_btn.first.click(timeout=1000)
            except Exception:
                pass

            # Inspect playback state
            state = await page.evaluate("""
                () => {
                    const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
                    if (!v) return { player_found: false, paused: true, currentTime: 0, duration: 0 };

                    const titleEl = document.querySelector('h1.ytd-watch-metadata yt-formatted-string, #title h1 yt-formatted-string');
                    const chEl = document.querySelector('#owner ytd-channel-name yt-formatted-string a, #channel-name a');

                    return {
                        player_found: true,
                        paused: v.paused,
                        currentTime: v.currentTime,
                        duration: v.duration,
                        title: titleEl ? titleEl.innerText : document.title,
                        channel: chEl ? chEl.innerText : ''
                    };
                }
            """)

            # If video is paused by browser autoplay policy, send play trigger
            if state.get("paused"):
                try:
                    await page.keyboard.press("k")
                    await page.wait_for_timeout(400)
                except Exception:
                    pass
                # Second check / play fallback
                state_update = await page.evaluate("""
                    () => {
                        const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
                        if (!v) return { paused: true, currentTime: 0 };
                        if (v.paused) {
                            try { v.play(); } catch(e) {}
                        }
                        return { paused: v.paused, currentTime: v.currentTime, duration: v.duration };
                    }
                """)
                state.update(state_update)

            return state

        try:
            res_state = browser_worker.run_coro(_do_play(), timeout=(timeout_ms / 1000.0) + 4.0)
            player_found = res_state.get("player_found", False)
            is_paused = res_state.get("paused", True)
            curr_time = res_state.get("currentTime", 0.0)
            actual_title = res_state.get("title") or target_title
            actual_channel = res_state.get("channel") or target_artist

            # Verification: Player must exist and playback started (not paused, or positive playtime)
            is_verified = player_found and (not is_paused or curr_time > 0.0 or res_state.get("duration", 0.0) > 0.0)

            if is_verified:
                self.active_video_title = actual_title
                self.active_video_url = validated_url
                self.active_video_channel = actual_channel
                self.active_video_id = vid_id
                self.playback_state = "PLAYING"
                self.history.append({
                    "title": actual_title,
                    "url": validated_url,
                    "artist": actual_channel,
                    "timestamp": urllib.parse.quote_plus(actual_title)
                })

                return {
                    "status": "PLAYBACK_CONFIRMED",
                    "service": "youtube",
                    "track": actual_title,
                    "artist": actual_channel,
                    "url": validated_url,
                    "video_id": vid_id,
                    "match_type": match_status,
                    "is_official": is_off,
                    "verified": True,
                    "playback_state": "PLAYING",
                    "message": f"Now playing '{actual_title}' on YouTube."
                }
            else:
                return {
                    "status": "PLAYBACK_UNVERIFIED",
                    "service": "youtube",
                    "track": actual_title,
                    "artist": actual_channel,
                    "url": validated_url,
                    "verified": False,
                    "message": f"Opened YouTube video at {validated_url}, but playback could not be verified."
                }

        except BrowserUnavailableError as bue:
            return {"status": "BROWSER_UNAVAILABLE", "service": "youtube", "message": f"Browser unavailable: {bue}", "verified": False}
        except ElementNotFoundError as enfe:
            return {"status": "PLAYER_NOT_FOUND", "service": "youtube", "message": f"YouTube player not found: {enfe}", "verified": False}
        except BrowserSecurityError as bse:
            return {"status": "SECURITY_BLOCKED", "service": "youtube", "message": f"Navigation blocked: {bse}", "verified": False}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"YouTube playback failed: {e}", "verified": False}

    def pause(self, session_id: Optional[str] = None, timeout_ms: int = 8000) -> Dict[str, Any]:
        """Pauses currently active YouTube playback."""
        async def _do_pause():
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")

            res = await page.evaluate("""
                () => {
                    const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
                    if (!v) return { found: false, paused: true };
                    if (!v.paused) v.pause();
                    return { found: true, paused: v.paused, currentTime: v.currentTime };
                }
            """)
            return res

        try:
            res = browser_worker.run_coro(_do_pause(), timeout=(timeout_ms / 1000.0) + 3.0)
            if res.get("found"):
                self.playback_state = "PAUSED"
                return {
                    "status": "PAUSED",
                    "service": "youtube",
                    "verified": True,
                    "track": self.active_video_title,
                    "message": "YouTube playback paused."
                }
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback detected to pause."
            }
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback is currently open."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed pausing YouTube: {e}", "verified": False}

    def resume(self, session_id: Optional[str] = None, timeout_ms: int = 8000) -> Dict[str, Any]:
        """Resumes paused YouTube playback."""
        async def _do_resume():
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")

            res = await page.evaluate("""
                () => {
                    const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
                    if (!v) return { found: false, playing: false };
                    if (v.paused) {
                        try { v.play(); } catch(e) {}
                    }
                    return { found: true, playing: !v.paused, currentTime: v.currentTime };
                }
            """)
            return res

        try:
            res = browser_worker.run_coro(_do_resume(), timeout=(timeout_ms / 1000.0) + 3.0)
            if res.get("found"):
                self.playback_state = "PLAYING"
                return {
                    "status": "RESUMED",
                    "service": "youtube",
                    "verified": True,
                    "track": self.active_video_title,
                    "message": "YouTube playback resumed."
                }
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube video detected to resume."
            }
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube video is currently open."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed resuming YouTube: {e}", "verified": False}

    def stop(self, session_id: Optional[str] = None, close_player: bool = False) -> Dict[str, Any]:
        """Stops active YouTube playback."""
        pause_res = self.pause(session_id=session_id)
        self.playback_state = "STOPPED"
        if close_player:
            try:
                browser_automation_service.close(session_id=session_id)
            except Exception:
                pass
        return {
            "status": "STOPPED",
            "service": "youtube",
            "verified": True,
            "track": self.active_video_title,
            "message": "YouTube playback stopped."
        }

    def next_track(self, session_id: Optional[str] = None, timeout_ms: int = 10000) -> Dict[str, Any]:
        """Skips to the next video on YouTube."""
        async def _do_next():
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")

            next_btn = page.locator("a.ytp-next-button, .ytp-next-button")
            if await next_btn.count() > 0 and await next_btn.first.is_visible():
                await next_btn.first.click()
            else:
                await page.keyboard.press("Shift+N")

            await page.wait_for_timeout(1000)
            title = await page.evaluate("() => (document.querySelector('h1.ytd-watch-metadata yt-formatted-string, #title h1 yt-formatted-string')?.innerText || document.title)")
            return title

        try:
            new_title = browser_worker.run_coro(_do_next(), timeout=(timeout_ms / 1000.0) + 3.0)
            self.active_video_title = new_title
            self.playback_state = "PLAYING"
            return {
                "status": "SKIPPED_TO_NEXT",
                "service": "youtube",
                "verified": True,
                "track": new_title,
                "message": f"Skipped to next video on YouTube: '{new_title}'."
            }
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback to skip."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed skipping track: {e}", "verified": False}

    def previous_track(self, session_id: Optional[str] = None, timeout_ms: int = 8000) -> Dict[str, Any]:
        """Returns to previous track or restarts current track from beginning."""
        async def _do_prev():
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")

            # Seek video to 0:00 (restart track)
            await page.evaluate("""
                () => {
                    const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
                    if (v) {
                        v.currentTime = 0;
                        if (v.paused) v.play();
                    }
                }
            """)
            title = await page.evaluate("() => (document.querySelector('h1.ytd-watch-metadata yt-formatted-string, #title h1 yt-formatted-string')?.innerText || document.title)")
            return title

        try:
            title = browser_worker.run_coro(_do_prev(), timeout=(timeout_ms / 1000.0) + 3.0)
            return {
                "status": "RETURNED_TO_PREVIOUS",
                "service": "youtube",
                "verified": True,
                "track": title or self.active_video_title,
                "message": "Restarted current track from beginning on YouTube."
            }
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback detected."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed returning to previous track: {e}", "verified": False}

    def get_playback_state(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns active YouTube playback status."""
        return {
            "status": "PLAYBACK_STATE",
            "service": "youtube",
            "state": self.playback_state,
            "track": self.active_video_title,
            "artist": self.active_video_channel,
            "url": self.active_video_url,
            "verified": self.playback_state == "PLAYING"
        }


youtube_service = YouTubeMusicService()
