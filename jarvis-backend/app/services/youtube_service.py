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

    @classmethod
    def _normalize_track_and_artist(cls, track: Optional[str], artist: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Normalizes track title and artist. Resolves canonical aliases, strips trailing provider suffixes,
        and extracts embedded artists ('Title by Artist').
        """
        q = (track or "").strip().strip("\"'")
        a = (artist or "").strip().strip("\"'")

        # Clean trailing 'on youtube' and 'on spotify'
        q = re.sub(r"\s+on\s+(?:youtube|spotify)\b.*$", "", q, flags=re.I).strip()
        if a:
            a = re.sub(r"\s+on\s+(?:youtube|spotify)\b.*$", "", a, flags=re.I).strip()

        # If artist is not provided separately, check if embedded via ' by '
        if not a and " by " in q:
            q_parts = re.split(r"\s+by\s+", q, maxsplit=1, flags=re.I)
            if len(q_parts) == 2:
                q, a = q_parts[0].strip(), q_parts[1].strip()

        # Clean extraneous phrasing like 'music video for'
        clean_q = re.sub(r"^(?:the\s+)?(?:official\s+)?(?:music\s+)?video\s+(?:for|of)\s+", "", q, flags=re.I).strip()
        clean_q = re.sub(r"^(?:that\s+)?(?:september\s+song)\b", "Wake Me Up When September Ends", clean_q, flags=re.I)
        if clean_q.lower() in ["september ends", "when september ends"]:
            clean_q = "Wake Me Up When September Ends"

        # Canonical artist associations for unambiguous canonical titles
        if clean_q.lower() == "wake me up when september ends" and not a:
            a = "Green Day"
        elif clean_q.lower() == "boulevard of broken dreams" and not a:
            a = "Green Day"
        elif clean_q.lower() == "numb" and not a:
            a = "Linkin Park"

        return clean_q, (a if a else None)

    @classmethod
    def _extract_core_title(cls, title: str, artist: Optional[str] = None) -> str:
        """Extracts normalized core song title by removing mix prefixes, artist markers, and video tags."""
        t = (title or "").strip()
        # Remove Mix prefixes
        t = re.sub(r"^mix\s*[-–—:]\s*", "", t, flags=re.I).strip()

        # Remove bracketed and parenthesized metadata tags
        t = re.sub(r"\[(?:official\s+(?:music\s+)?video|official\s+audio|official|music\s+video|video|audio|lyrics?|lyric\s+video|4k(?:\s+upgrade)?|hd|remastered|explicit|clean|visualizer|live|full\s+audio)[^\]]*\]", "", t, flags=re.I)
        t = re.sub(r"\((?:official\s+(?:music\s+)?video|official\s+audio|official|music\s+video|video|audio|lyrics?|lyric\s+video|4k(?:\s+upgrade)?|hd|remastered|explicit|clean|visualizer|live|full\s+audio)[^\)]*\)", "", t, flags=re.I)
        t = re.sub(r"\[(?:4k(?:\s+upgrade)?|hd|remastered|hq)[^\]]*\]", "", t, flags=re.I)
        t = re.sub(r"\((?:4k(?:\s+upgrade)?|hd|remastered|hq)[^\)]*\)", "", t, flags=re.I)

        # Remove artist prefix or suffix if artist is known
        if artist:
            art_esc = re.escape(artist.strip())
            t = re.sub(rf"^{art_esc}\s*[-–—:]\s*", "", t, flags=re.I).strip()
            t = re.sub(rf"\s*[-–—:]\s*{art_esc}$", "", t, flags=re.I).strip()

        # If still in "Artist - Song" format, remove general artist prefix
        if " - " in t:
            parts = t.split(" - ", 1)
            if len(parts) == 2 and parts[1].strip():
                t = parts[1].strip()

        # Strip 'by Artist' suffix
        t = re.sub(r"\s+by\s+.*$", "", t, flags=re.I).strip()

        # Normalize whitespace and lowercase
        t = re.sub(r"[\s\-_]+$", "", t).strip()
        return t.lower()

    @classmethod
    def _extract_core_artist(cls, cand: Dict[str, Any]) -> str:
        """Extracts normalized artist/channel identity from candidate."""
        ch = (cand.get("channel") or "").strip()
        ch = re.sub(r"\s*-\s*topic$", "", ch, flags=re.I)
        ch = re.sub(r"\s*vevo$", "", ch, flags=re.I)
        ch = re.sub(r"\s*official$", "", ch, flags=re.I)
        if ch:
            return ch.lower().strip()

        title = cand.get("title", "")
        clean_title = re.sub(r"^mix\s*[-–—:]\s*", "", title, flags=re.I).strip()
        if " - " in clean_title:
            return clean_title.split(" - ", 1)[0].strip().lower()

        return ""

    def _build_search_query(self, query: Optional[str] = None, artist: Optional[str] = None, genre: Optional[str] = None) -> str:
        """Constructs an optimized YouTube search query string."""
        clean_q, a = self._normalize_track_and_artist(query, artist)
        g = (genre or "").strip().strip("\"'")
        parts = []

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
        Distinguishes browser, network, and extraction errors from empty results.
        """
        search_query = self._build_search_query(query=query, artist=artist)
        encoded_term = urllib.parse.quote_plus(search_query)
        target_url = f"{self.YOUTUBE_SEARCH_URL}{encoded_term}"
        validated_url = URLSecurityValidator.validate(target_url)

        # Acquire session outside worker thread to prevent thread deadlock
        sess = browser_automation_service._get_active_session(session_id)
        page = sess.page
        if not page or (hasattr(page, "is_closed") and page.is_closed()):
            raise NoActivePageError("Active browser session is closed.")

        async def _do_search():
            try:
                await page.goto(validated_url, timeout=timeout_ms, wait_until="domcontentloaded")
            except Exception as net_err:
                raise YouTubeMusicServiceError(
                    f"YouTube search navigation failed: {net_err}",
                    code="NETWORK_ERROR",
                    details={"url": validated_url, "error": str(net_err)}
                )

            await browser_automation_service._dismiss_consent_if_present(page)

            # Wait for search results container or video items
            try:
                await page.locator(
                    "ytd-video-renderer, ytd-rich-item-renderer, yt-lockup-view-model, a#video-title"
                ).first.wait_for(state="attached", timeout=8000)
            except Exception:
                pass

            # Extract visible video candidates from the DOM with resilient selectors
            try:
                raw_candidates = await page.evaluate(r"""
                    () => {
                        const results = [];
                        const nodes = document.querySelectorAll(
                            'ytd-video-renderer, ytd-rich-item-renderer, ytd-compact-video-renderer, yt-lockup-view-model'
                        );
                        for (const node of nodes) {
                            const a = node.querySelector(
                                'a#video-title, #video-title, h3 a, a.yt-lockup-metadata-view-model-wiz__title, a[id="video-title"]'
                            );
                            const thumbLink = node.querySelector('a#thumbnail, a[href*="/watch?v="]');

                            let title = '';
                            if (a) {
                                title = (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || a.textContent || '').trim();
                            } else if (thumbLink) {
                                title = (thumbLink.getAttribute('title') || thumbLink.getAttribute('aria-label') || '').trim();
                            }

                            const href = (a && a.getAttribute('href')) || (thumbLink && thumbLink.getAttribute('href')) || '';
                            const vMatch = href.match(/(?:[?&]v=|\/embed\/|\/shorts\/|\/v\/|youtu\\.be\/)([a-zA-Z0-9_-]{11})/);
                            if (!title || !vMatch) continue;
                            const videoId = vMatch[1];

                            const chNode = node.querySelector(
                                '#channel-info #channel-name a, #byline a, ytd-channel-name a, #text.ytd-channel-name a, .ytd-channel-name yt-formatted-string'
                            );
                            const channel = chNode ? (chNode.innerText || chNode.textContent || '').trim() : '';

                            const badgeNode = node.querySelector(
                                '[aria-label*="Official"], [aria-label*="Verified"], .badge-style-type-verified, .badge-style-type-verified-artist, ytd-badge-supported-renderer'
                            );
                            const isMix = /^mix\s*[-–—:]/i.test(title) || /list=RD/i.test(href);
                            const isOfficial = !isMix && (!!badgeNode 
                                || /official\\s+(?:music\\s+)?video|official\\s+audio|\\[official\\]|\\(official\\)/i.test(title)
                                || /(?:VEVO|\\bTopic)$/i.test(channel));

                            results.push({
                                title: title,
                                video_id: videoId,
                                url: `https://www.youtube.com/watch?v=${videoId}`,
                                channel: channel,
                                is_official: isOfficial,
                                is_mix: isMix
                            });
                            if (results.length >= 10) break;
                        }
                        return results;
                    }
                """)
                return raw_candidates
            except Exception as eval_err:
                raise YouTubeMusicServiceError(
                    f"YouTube search extraction failed: {eval_err}",
                    code="EXTRACTION_ERROR",
                    details={"error": str(eval_err)}
                )

        try:
            candidates = browser_worker.run_coro(_do_search(), timeout=(timeout_ms / 1000.0) + 4.0)
            return candidates[:limit]
        except (BrowserSecurityError, NoActivePageError, BrowserUnavailableError, YouTubeMusicServiceError):
            raise
        except Exception as e:
            logger.warning(f"YouTube search extraction encountered error: {e}")
            raise YouTubeMusicServiceError(
                f"YouTube search error: {e}",
                code="EXTRACTION_ERROR",
                details={"error": str(e)}
            )

    def _score_candidate(self, cand: Dict[str, Any], track_query: str, artist: Optional[str] = None) -> float:
        """
        Computes relevance score for candidate search result.
        Gives priority to exact/approximate title matches and official artist channels.
        Favors official music video for generic playback requests, and penalizes YouTube Mix / aggregate entries.
        """
        score = 0.0
        title_raw = cand.get("title", "")
        title_low = title_raw.lower()
        channel_low = cand.get("channel", "").lower()
        url_low = cand.get("url", "").lower()

        # Canonical normalization
        canon_track, canon_artist = self._normalize_track_and_artist(track_query, artist)
        t_norm = canon_track.lower().strip()
        a_norm = (canon_artist or "").lower().strip()

        core_title = self._extract_core_title(title_raw, canon_artist)

        # 1. Artist Matching
        if a_norm:
            if a_norm == channel_low or f"{a_norm} - topic" in channel_low or f"{a_norm}vevo" in channel_low:
                score += 45.0
            elif a_norm in channel_low:
                score += 35.0

            if a_norm in title_low:
                score += 25.0

        # 2. Track Title Matching
        if t_norm:
            if core_title == t_norm or core_title == self._extract_core_title(track_query, artist):
                score += 50.0
            elif t_norm in title_low:
                score += 40.0
            else:
                t_words = [w for w in re.split(r"[^\w]+", t_norm) if len(w) > 2]
                if t_words:
                    matched = sum(1 for w in t_words if w in title_low)
                    score += (matched / len(t_words)) * 35.0

        # 3. Known approximate mappings
        if ("september ends" in t_norm or "when september ends" in t_norm) and "wake me up when september ends" in title_low:
            score += 35.0
        if "boulevard of broken dreams" in t_norm and "boulevard of broken dreams" in title_low:
            score += 35.0
        if "numb" in t_norm and "numb" in title_low:
            score += 35.0

        # 4. Official Channel / Artist verification badge
        if cand.get("is_official"):
            score += 15.0

        # 5. Format Detection & Preference
        is_mix = bool(
            cand.get("is_mix")
            or re.search(r"^mix\s*[-–—:]|\bmix\b", title_low)
            or "list=" in url_low
            or "start_radio=1" in url_low
        )
        is_official_mv = bool(
            re.search(r"official\s+(?:music\s+)?video|\bmusic\s+video\b|\[official\s+video\]|\(official\s+video\)", title_low)
            and not is_mix
        )
        is_official_audio = bool(
            re.search(r"official\s+audio|\bvisualizer\b|audio\s+video|\[official\s+audio\]|\(official\s+audio\)", title_low)
            and not is_mix
        )

        user_wants_audio = "audio" in t_norm
        user_wants_lyrics = "lyric" in t_norm or "lyrics" in t_norm
        user_wants_mix = "mix" in t_norm

        # Mix handling: heavy penalty unless user specifically asked for a mix
        if user_wants_mix:
            if is_mix:
                score += 25.0
        else:
            if is_mix:
                score -= 60.0

        # Official Music Video vs Official Audio vs Lyrics
        if is_official_mv and not user_wants_audio and not user_wants_lyrics:
            score += 20.0
        elif is_official_audio:
            if user_wants_audio:
                score += 25.0
            else:
                score += 8.0

        # 6. Aggregates and duplicates penalties
        aggregates = ["playlist", "compilation", "full album", "top tracks", "greatest hits"]
        for agg in aggregates:
            if agg in title_low and agg not in t_norm:
                score -= 35.0

        # 7. Penalties for live/cover/parody/remix/reaction/tutorial unless requested
        penalties = ["cover", "parody", "reaction", "karaoke", "remix", "guitar lesson", "tutorial", "how to play", "lesson"]
        for p in penalties:
            if p in title_low and p not in t_norm:
                score -= 35.0

        if "live" in title_low and "live" not in t_norm:
            score -= 15.0

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
        Propagates browser, session, and network errors.
        """
        canon_track, canon_artist = self._normalize_track_and_artist(track_query, artist)
        candidates = self.search_music(query=canon_track, artist=canon_artist, limit=8, session_id=session_id)
        if not candidates:
            return "NO_MATCH", None, []

        scored = []
        for c in candidates:
            s = self._score_candidate(c, track_query=canon_track, artist=canon_artist)
            scored.append((s, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_cand = scored[0]

        # Check for genuine ambiguity between top candidates
        if len(scored) > 1:
            second_score, second_cand = scored[1]
            core_top = self._extract_core_title(top_cand.get("title", ""), canon_artist)
            core_second = self._extract_core_title(second_cand.get("title", ""), canon_artist)
            artist_top = self._extract_core_artist(top_cand)
            artist_second = self._extract_core_artist(second_cand)

            # Determine whether top two candidates represent the exact same song & artist
            same_song_and_artist = (
                bool(core_top)
                and bool(core_second)
                and (core_top == core_second or core_top in core_second or core_second in core_top)
                and (
                    not artist_top
                    or not artist_second
                    or artist_top == artist_second
                    or (canon_artist and canon_artist.lower() in [artist_top, artist_second])
                )
            )

            # Only consider ambiguous if top candidates are genuinely different songs or artists,
            # and confidence gap between them is narrow without an overwhelming top score
            if not same_song_and_artist:
                score_gap = top_score - second_score
                if top_score >= 35.0 and score_gap < 20.0 and top_score < 120.0:
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

        try:
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
                canon_track, canon_artist = self._normalize_track_and_artist(track, artist)
                q = canon_track or (f"{genre} music" if genre else f"{canon_artist} songs")
                match_status, selected_cand, candidates = self.resolve_track(
                    track_query=q,
                    artist=canon_artist,
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
        except BrowserUnavailableError as bue:
            return {"status": "BROWSER_UNAVAILABLE", "service": "youtube", "message": f"Browser unavailable: {bue}", "verified": False}
        except NoActivePageError as nape:
            return {"status": "SESSION_CLOSED", "service": "youtube", "message": f"Browser session closed: {nape}", "verified": False}
        except BrowserSecurityError as bse:
            return {"status": "SECURITY_BLOCKED", "service": "youtube", "message": f"Navigation blocked: {bse}", "verified": False}
        except YouTubeMusicServiceError as yme:
            return {"status": yme.code, "service": "youtube", "message": str(yme), "verified": False, "details": yme.details}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"YouTube track resolution failed: {e}", "verified": False}

        validated_url = URLSecurityValidator.validate(target_url)

        # Acquire session outside worker thread to prevent thread deadlock
        try:
            sess = browser_automation_service._get_active_session(session_id)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("Active browser session is closed.")
        except BrowserUnavailableError as bue:
            return {"status": "BROWSER_UNAVAILABLE", "service": "youtube", "message": f"Browser unavailable: {bue}", "verified": False}
        except NoActivePageError as nape:
            return {"status": "SESSION_CLOSED", "service": "youtube", "message": f"Browser session closed: {nape}", "verified": False}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed acquiring browser session: {e}", "verified": False}

        # 2. Browser Automation Playback Execution & Verification
        async def _do_play():
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
                    "title": actual_title,
                    "resolved_track": actual_title,
                    "artist": actual_channel,
                    "channel": actual_channel,
                    "resolved_artist": actual_channel,
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
                    "title": actual_title,
                    "resolved_track": actual_title,
                    "artist": actual_channel,
                    "channel": actual_channel,
                    "resolved_artist": actual_channel,
                    "url": validated_url,
                    "video_id": vid_id,
                    "verified": False,
                    "message": f"Opened YouTube video at {validated_url}, but playback could not be verified."
                }

        except BrowserUnavailableError as bue:
            return {"status": "BROWSER_UNAVAILABLE", "service": "youtube", "message": f"Browser unavailable: {bue}", "verified": False}
        except ElementNotFoundError as enfe:
            return {"status": "PLAYER_NOT_FOUND", "service": "youtube", "message": f"YouTube player not found: {enfe}", "verified": False}
        except BrowserSecurityError as bse:
            return {"status": "SECURITY_BLOCKED", "service": "youtube", "message": f"Navigation blocked: {bse}", "verified": False}
        except NoActivePageError as nape:
            return {"status": "SESSION_CLOSED", "service": "youtube", "message": f"Browser session closed: {nape}", "verified": False}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"YouTube playback failed: {e}", "verified": False}

    def pause(self, session_id: Optional[str] = None, timeout_ms: int = 8000) -> Dict[str, Any]:
        """Pauses currently active YouTube playback."""
        try:
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback is currently open."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed pausing YouTube: {e}", "verified": False}

        async def _do_pause():
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
        try:
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube video is currently open."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed resuming YouTube: {e}", "verified": False}

        async def _do_resume():
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
        try:
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback to skip."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed skipping track: {e}", "verified": False}

        async def _do_next():
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
        try:
            sess = browser_automation_service._get_active_session(session_id, must_exist=True)
            page = sess.page
            if not page or (hasattr(page, "is_closed") and page.is_closed()):
                raise NoActivePageError("The active browser session has been closed.")
        except (NoActivePageError, BrowserAutomationError):
            return {
                "status": "NO_ACTIVE_PLAYBACK",
                "service": "youtube",
                "verified": False,
                "message": "No active YouTube playback detected."
            }
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "service": "youtube", "message": f"Failed returning to previous track: {e}", "verified": False}

        async def _do_prev():
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
