import os
import re
import time
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple
import httpx

from app.core.config import settings

logger = logging.getLogger("jarvis.services.spotify")


class SpotifyServiceError(Exception):
    """Base exception for Spotify service operations."""
    def __init__(self, message: str, code: str = "PROVIDER_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class SpotifyMusicService:
    """
    Official Spotify Web API Integration Service.
    Handles authentication, catalog search, fuzzy track matching,
    device discovery, playback control, volume adjustment, and playback verification.
    """

    SPOTIFY_API_BASE = "https://api.spotify.com/v1"
    SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

    def __init__(self):
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        """Checks if minimal required Spotify credentials or tokens are present."""
        if hasattr(self, "_is_configured_override"):
            return self._is_configured_override
        has_client = bool(settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET)
        has_token = bool(settings.SPOTIFY_ACCESS_TOKEN or settings.SPOTIFY_REFRESH_TOKEN)
        return settings.SPOTIFY_ENABLED and (has_client or has_token)

    @is_configured.setter
    def is_configured(self, val: bool):
        self._is_configured_override = val

    @is_configured.deleter
    def is_configured(self):
        if hasattr(self, "_is_configured_override"):
            del self._is_configured_override

    def _get_auth_headers(self) -> Dict[str, str]:
        token = self._resolve_access_token()
        if not token:
            raise SpotifyServiceError(
                "Spotify is not configured. Please add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET or SPOTIFY_ACCESS_TOKEN in your .env file.",
                code="AUTHENTICATION_REQUIRED"
            )
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def _resolve_access_token(self) -> Optional[str]:
        # Direct access token from settings or environment
        if settings.SPOTIFY_ACCESS_TOKEN:
            return settings.SPOTIFY_ACCESS_TOKEN

        # Return cached valid token if unexpired
        if self._cached_token and time.time() < self._token_expires_at:
            return self._cached_token

        # Attempt token refresh if client credentials + refresh token exist
        if settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET and settings.SPOTIFY_REFRESH_TOKEN:
            try:
                auth_str = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
                b64_auth = base64.b64encode(auth_str.encode()).decode()
                headers = {
                    "Authorization": f"Basic {b64_auth}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                data = {
                    "grant_type": "refresh_token",
                    "refresh_token": settings.SPOTIFY_REFRESH_TOKEN
                }
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(self.SPOTIFY_TOKEN_URL, headers=headers, data=data)
                    if resp.status_code == 200:
                        payload = resp.json()
                        self._cached_token = payload.get("access_token")
                        expires_in = payload.get("expires_in", 3600)
                        self._token_expires_at = time.time() + (expires_in - 60)
                        return self._cached_token
                    else:
                        logger.warning(f"Spotify token refresh returned {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Spotify token refresh exception: {e}")

        # If only client credentials exist (Client Credentials Flow - catalog search only)
        if settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_CLIENT_SECRET:
            try:
                auth_str = f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}"
                b64_auth = base64.b64encode(auth_str.encode()).decode()
                headers = {
                    "Authorization": f"Basic {b64_auth}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                data = {"grant_type": "client_credentials"}
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(self.SPOTIFY_TOKEN_URL, headers=headers, data=data)
                    if resp.status_code == 200:
                        payload = resp.json()
                        self._cached_token = payload.get("access_token")
                        expires_in = payload.get("expires_in", 3600)
                        self._token_expires_at = time.time() + (expires_in - 60)
                        return self._cached_token
            except Exception as e:
                logger.error(f"Spotify client credentials flow exception: {e}")

        return None

    def get_devices(self) -> List[Dict[str, Any]]:
        """Retrieves list of active/available Spotify playback devices."""
        if not self.is_configured:
            return []
        headers = self._get_auth_headers()
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(f"{self.SPOTIFY_API_BASE}/me/player/devices", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("devices", [])
                elif res.status_code == 401:
                    raise SpotifyServiceError("Spotify token expired or invalid.", code="AUTHENTICATION_REQUIRED")
                elif res.status_code == 403:
                    raise SpotifyServiceError("Insufficient permissions for Spotify player control.", code="PERMISSIONS_REQUIRED")
        except SpotifyServiceError:
            raise
        except Exception as e:
            logger.warning(f"Error fetching Spotify devices: {e}")
        return []

    def get_playback_state(self) -> Optional[Dict[str, Any]]:
        """Retrieves the current player playback state."""
        if not self.is_configured:
            return None
        headers = self._get_auth_headers()
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(f"{self.SPOTIFY_API_BASE}/me/player", headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    item = data.get("item") or {}
                    artists = ", ".join([a.get("name", "") for a in item.get("artists", [])])
                    return {
                        "is_playing": data.get("is_playing", False),
                        "device": data.get("device", {}).get("name", "Unknown Device"),
                        "device_id": data.get("device", {}).get("id"),
                        "track_name": item.get("name"),
                        "artist": artists,
                        "album": item.get("album", {}).get("name"),
                        "uri": item.get("uri"),
                        "progress_ms": data.get("progress_ms"),
                        "duration_ms": item.get("duration_ms"),
                        "volume_percent": data.get("device", {}).get("volume_percent")
                    }
                elif res.status_code == 204:
                    return {"is_playing": False, "device": None, "track_name": None}
                elif res.status_code == 401:
                    raise SpotifyServiceError("Spotify token expired or invalid.", code="AUTHENTICATION_REQUIRED")
        except SpotifyServiceError:
            raise
        except Exception as e:
            logger.warning(f"Error getting Spotify playback state: {e}")
        return None

    def search_catalog(
        self,
        query: str,
        artist: Optional[str] = None,
        search_type: str = "track",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Searches the Spotify catalog with support for approximate track matching.
        """
        if not self.is_configured:
            raise SpotifyServiceError(
                "Spotify credentials are not configured. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.",
                code="NOT_CONFIGURED"
            )

        q = query.strip()
        if artist and artist.lower() not in q.lower():
            q = f"track:{q} artist:{artist.strip()}"

        headers = self._get_auth_headers()
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(
                    f"{self.SPOTIFY_API_BASE}/search",
                    headers=headers,
                    params={"q": q, "type": search_type, "limit": limit}
                )
                if res.status_code == 200:
                    data = res.json()
                    tracks = data.get("tracks", {}).get("items", [])
                    results = []
                    for t in tracks:
                        track_artists = ", ".join([a.get("name", "") for a in t.get("artists", [])])
                        results.append({
                            "id": t.get("id"),
                            "name": t.get("name"),
                            "artist": track_artists,
                            "album": t.get("album", {}).get("name"),
                            "uri": t.get("uri"),
                            "duration_ms": t.get("duration_ms"),
                            "popularity": t.get("popularity", 0)
                        })
                    return results
                elif res.status_code == 401:
                    raise SpotifyServiceError("Spotify access token is expired or unauthorized.", code="AUTHENTICATION_REQUIRED")
                else:
                    raise SpotifyServiceError(f"Spotify search failed with status {res.status_code}: {res.text}", code="PROVIDER_ERROR")
        except SpotifyServiceError:
            raise
        except Exception as e:
            logger.error(f"Spotify catalog search exception: {e}")
            raise SpotifyServiceError(f"Spotify catalog search failed: {e}", code="PROVIDER_ERROR")

    def resolve_track(
        self,
        track_query: str,
        artist: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], str, List[Dict[str, Any]]]:
        """
        Resolves a user-requested song or approximate title to a specific Spotify track.
        Handles approximate phrasing (e.g. 'September Ends' -> 'Wake Me Up When September Ends').
        Returns: (selected_track, status, candidate_matches)
        Status: 'EXACT_MATCH', 'FUZZY_MATCH', 'AMBIGUOUS_MATCH', 'NO_MATCH'
        """
        norm_query = track_query.strip().lower()
        candidates = self.search_catalog(query=track_query, artist=artist, limit=5)

        if not candidates and artist:
            # Fallback search by artist alone or broad query
            candidates = self.search_catalog(query=f"{track_query} {artist}", limit=5)

        if not candidates:
            return None, "NO_MATCH", []

        # 1. Check for exact title match
        for cand in candidates:
            if cand["name"].lower() == norm_query:
                if not artist or artist.lower() in cand["artist"].lower():
                    return cand, "EXACT_MATCH", candidates

        # 2. Approximate / substring title match
        # e.g., 'september ends' in 'wake me up when september ends'
        words = [w for w in re.findall(r"\w+", norm_query) if len(w) > 2]
        scored_candidates = []
        for cand in candidates:
            cand_name_low = cand["name"].lower()
            score = 0
            if norm_query in cand_name_low:
                score += 10
            for w in words:
                if w in cand_name_low:
                    score += 2
            if artist and artist.lower() in cand["artist"].lower():
                score += 8
            scored_candidates.append((score, cand))

        scored_candidates.sort(key=lambda x: (x[0], x[1]["popularity"]), reverse=True)

        if scored_candidates and scored_candidates[0][0] >= 6:
            top_score = scored_candidates[0][0]
            top_cand = scored_candidates[0][1]

            # Check for ambiguity: if second candidate has equal or near-identical score with different title
            if len(scored_candidates) > 1 and scored_candidates[1][0] == top_score:
                second_cand = scored_candidates[1][1]
                if second_cand["name"].lower() != top_cand["name"].lower():
                    return None, "AMBIGUOUS_MATCH", [c[1] for c in scored_candidates[:3]]

            return top_cand, "FUZZY_MATCH", candidates

        return candidates[0], "FUZZY_MATCH", candidates

    def play(
        self,
        uri: Optional[str] = None,
        context_uri: Optional[str] = None,
        uris: Optional[List[str]] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Starts or resumes playback on an active Spotify device.
        """
        if not self.is_configured:
            return {
                "status": "AUTHENTICATION_REQUIRED",
                "message": "Spotify is not configured. Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET or access token in .env.",
                "verified": False
            }

        headers = self._get_auth_headers()
        dev_id = device_id or settings.SPOTIFY_DEFAULT_DEVICE_ID
        
        # Check active devices if no specific device specified
        if not dev_id:
            devices = self.get_devices()
            active_dev = next((d for d in devices if d.get("is_active")), None)
            if active_dev:
                dev_id = active_dev.get("id")
            elif devices:
                dev_id = devices[0].get("id")
            else:
                return {
                    "status": "NO_ACTIVE_DEVICE",
                    "message": "No active Spotify playback device found. Please open Spotify on your computer or phone first.",
                    "verified": False
                }

        body: Dict[str, Any] = {}
        if uri:
            if ":track:" in uri:
                body["uris"] = [uri]
            else:
                body["context_uri"] = uri
        elif uris:
            body["uris"] = uris
        elif context_uri:
            body["context_uri"] = context_uri

        params = {}
        if dev_id:
            params["device_id"] = dev_id

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.put(
                    f"{self.SPOTIFY_API_BASE}/me/player/play",
                    headers=headers,
                    params=params,
                    json=body if body else None
                )
                if res.status_code in [200, 204]:
                    # Brief verification check
                    time.sleep(0.3)
                    state = self.get_playback_state()
                    track_name = state.get("track_name") if state else None
                    artist_name = state.get("artist") if state else None
                    return {
                        "status": "PLAYBACK_CONFIRMED",
                        "message": f"Now playing {track_name} by {artist_name}" if track_name else "Playback started on Spotify.",
                        "verified": True,
                        "track": track_name,
                        "artist": artist_name,
                        "uri": uri
                    }
                elif res.status_code == 404:
                    return {
                        "status": "NO_ACTIVE_DEVICE",
                        "message": "No active Spotify player found to start playback.",
                        "verified": False
                    }
                elif res.status_code == 403:
                    return {
                        "status": "PLAYBACK_UNAVAILABLE",
                        "message": "Spotify playback control requires a Spotify Premium subscription and an active player device.",
                        "verified": False
                    }
                elif res.status_code == 401:
                    return {
                        "status": "AUTHENTICATION_REQUIRED",
                        "message": "Spotify authentication expired or unauthorized.",
                        "verified": False
                    }
                else:
                    return {
                        "status": "PROVIDER_ERROR",
                        "message": f"Spotify API error ({res.status_code}): {res.text}",
                        "verified": False
                    }
        except Exception as e:
            logger.error(f"Spotify play request error: {e}")
            return {
                "status": "PROVIDER_ERROR",
                "message": f"Could not send playback command to Spotify: {e}",
                "verified": False
            }

    def pause(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Pauses current Spotify playback."""
        if not self.is_configured:
            return {
                "status": "AUTHENTICATION_REQUIRED",
                "message": "Spotify is not configured.",
                "verified": False
            }

        headers = self._get_auth_headers()
        params = {}
        if device_id:
            params["device_id"] = device_id

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.put(f"{self.SPOTIFY_API_BASE}/me/player/pause", headers=headers, params=params)
                if res.status_code in [200, 204]:
                    return {
                        "status": "PLAYBACK_PAUSED",
                        "message": "Spotify playback paused.",
                        "verified": True
                    }
                elif res.status_code == 404:
                    return {
                        "status": "NO_ACTIVE_DEVICE",
                        "message": "No active Spotify device to pause.",
                        "verified": False
                    }
                elif res.status_code == 403:
                    return {
                        "status": "PLAYBACK_UNAVAILABLE",
                        "message": "Cannot pause Spotify playback (Premium required or restriction active).",
                        "verified": False
                    }
                else:
                    return {
                        "status": "PROVIDER_ERROR",
                        "message": f"Spotify error ({res.status_code}): {res.text}",
                        "verified": False
                    }
        except Exception as e:
            return {
                "status": "PROVIDER_ERROR",
                "message": f"Failed to pause Spotify: {e}",
                "verified": False
            }

    def resume(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Resumes paused Spotify playback."""
        return self.play(device_id=device_id)

    def next_track(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Skips to the next track on Spotify."""
        if not self.is_configured:
            return {"status": "AUTHENTICATION_REQUIRED", "message": "Spotify is not configured.", "verified": False}

        headers = self._get_auth_headers()
        params = {}
        if device_id:
            params["device_id"] = device_id

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.post(f"{self.SPOTIFY_API_BASE}/me/player/next", headers=headers, params=params)
                if res.status_code in [200, 204]:
                    time.sleep(0.3)
                    state = self.get_playback_state()
                    track = state.get("track_name") if state else None
                    artist = state.get("artist") if state else None
                    return {
                        "status": "TRACK_SKIPPED",
                        "message": f"Skipped to next track: {track} by {artist}" if track else "Skipped to next track.",
                        "verified": True,
                        "track": track,
                        "artist": artist
                    }
                else:
                    return {"status": "PROVIDER_ERROR", "message": f"Failed to skip track: {res.text}", "verified": False}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "message": f"Failed to skip track: {e}", "verified": False}

    def previous_track(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns to the previous track on Spotify."""
        if not self.is_configured:
            return {"status": "AUTHENTICATION_REQUIRED", "message": "Spotify is not configured.", "verified": False}

        headers = self._get_auth_headers()
        params = {}
        if device_id:
            params["device_id"] = device_id

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.post(f"{self.SPOTIFY_API_BASE}/me/player/previous", headers=headers, params=params)
                if res.status_code in [200, 204]:
                    time.sleep(0.3)
                    state = self.get_playback_state()
                    track = state.get("track_name") if state else None
                    artist = state.get("artist") if state else None
                    return {
                        "status": "TRACK_PREVIOUS",
                        "message": f"Returned to previous track: {track} by {artist}" if track else "Returned to previous track.",
                        "verified": True,
                        "track": track,
                        "artist": artist
                    }
                else:
                    return {"status": "PROVIDER_ERROR", "message": f"Failed to go to previous track: {res.text}", "verified": False}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "message": f"Failed to go to previous track: {e}", "verified": False}

    def set_volume(self, volume_percent: int, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Sets Spotify playback volume (0 - 100)."""
        if not self.is_configured:
            return {"status": "AUTHENTICATION_REQUIRED", "message": "Spotify is not configured.", "verified": False}

        vol = max(0, min(100, int(volume_percent)))
        headers = self._get_auth_headers()
        params = {"volume_percent": vol}
        if device_id:
            params["device_id"] = device_id

        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.put(f"{self.SPOTIFY_API_BASE}/me/player/volume", headers=headers, params=params)
                if res.status_code in [200, 204]:
                    return {
                        "status": "VOLUME_SET",
                        "message": f"Spotify volume set to {vol}%.",
                        "verified": True,
                        "volume": vol
                    }
                else:
                    return {"status": "PROVIDER_ERROR", "message": f"Failed to set volume: {res.text}", "verified": False}
        except Exception as e:
            return {"status": "PROVIDER_ERROR", "message": f"Failed to set volume: {e}", "verified": False}


spotify_service = SpotifyMusicService()
