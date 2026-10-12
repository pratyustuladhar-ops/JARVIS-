import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.ai.agent import jarvis_agent
from app.ai.intent import intent_detector
from app.ai.planner import AgentPlanner
from app.ai.context import AgentContext
from app.services.youtube_service import youtube_service, YouTubeMusicServiceError
from app.services.spotify_service import spotify_service
from app.services.browser.automation_service import (
    browser_automation_service,
    BrowserUnavailableError,
    NoActivePageError,
    ElementNotFoundError
)
from app.services.browser.security import BrowserSecurityError
from app.core.config import settings

client = TestClient(app)


# ==================== 1. DEFAULT PROVIDER & ZERO SPOTIFY CREDENTIALS ====================

def test_01_youtube_is_default_music_provider():
    """Verify that settings default to YouTube as music provider."""
    assert getattr(settings, "MUSIC_PROVIDER", "youtube").lower() == "youtube"


def test_02_music_play_uses_youtube_without_spotify_credentials(db_session):
    """Verify music commands execute on YouTube without calling or requiring Spotify."""
    mock_play_result = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing 'Wake Me Up When September Ends' by Green Day on YouTube.",
        "verified": True,
        "resolved_track": "Wake Me Up When September Ends",
        "resolved_artist": "Green Day",
        "url": "https://www.youtube.com/watch?v=NU9JoFKbqZ0"
    }

    with patch.object(youtube_service, "play", return_value=mock_play_result) as mock_yt_play, \
         patch.object(spotify_service, "play") as mock_spotify_play:

        # Spotify is not configured, but command must succeed via YouTube
        res = jarvis_agent.process(db=db_session, message="Play September Ends by Green Day")

        assert res["verified"] is True
        assert res["actions"][0]["tool_name"] == "youtube_play"
        assert "green day" in res["response"].lower()
        assert "youtube" in res["response"].lower()
        mock_yt_play.assert_called_once()
        mock_spotify_play.assert_not_called()


# ==================== 2. NATURAL LANGUAGE MUSIC COMMAND VARIATIONS ====================

def test_03_nl_variations_route_to_youtube(db_session):
    """Verify various natural language commands route to YouTube tools without Spotify credentials."""
    mock_play_result = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing on YouTube.",
        "verified": True,
        "resolved_track": "Boulevard of Broken Dreams",
        "resolved_artist": "Green Day",
        "url": "https://www.youtube.com/watch?v=Soa3gO7tL-c"
    }

    with patch.object(youtube_service, "play", return_value=mock_play_result):
        # 1. Full title
        r1 = jarvis_agent.process(db=db_session, message="Play Wake Me Up When September Ends by Green Day.")
        assert r1["actions"][0]["tool_name"] == "youtube_play"

        # 2. Approximate title
        r2 = jarvis_agent.process(db=db_session, message="Can you play September Ends?")
        assert r2["actions"][0]["tool_name"] == "youtube_play"

        # 3. Another track
        r3 = jarvis_agent.process(db=db_session, message="Play Boulevard of Broken Dreams by Green Day.")
        assert r3["actions"][0]["tool_name"] == "youtube_play"

        # 4. Artist only
        r4 = jarvis_agent.process(db=db_session, message="Play some Green Day.")
        assert r4["actions"][0]["tool_name"] == "youtube_play"

        # 5. Genre only
        r5 = jarvis_agent.process(db=db_session, message="Play rock music.")
        assert r5["actions"][0]["tool_name"] == "youtube_play"


def test_04_nl_playback_controls_route_to_youtube(db_session):
    """Verify pause, resume, skip, previous, and stop route to YouTube controls."""
    with patch.object(youtube_service, "pause", return_value={"status": "PAUSED", "message": "YouTube playback paused.", "verified": True}), \
         patch.object(youtube_service, "resume", return_value={"status": "RESUMED", "message": "Resuming YouTube playback.", "verified": True}), \
         patch.object(youtube_service, "next_track", return_value={"status": "SKIPPED_TO_NEXT", "message": "Skipped to next track on YouTube.", "verified": True}), \
         patch.object(youtube_service, "previous_track", return_value={"status": "RETURNED_TO_PREVIOUS", "message": "Returned to previous track on YouTube.", "verified": True}), \
         patch.object(youtube_service, "stop", return_value={"status": "STOPPED", "message": "YouTube playback stopped.", "verified": True}):

        # Pause
        r_pause = jarvis_agent.process(db=db_session, message="Pause the music.")
        assert r_pause["actions"][0]["tool_name"] == "youtube_pause"
        assert "paused" in r_pause["response"].lower()

        # Resume
        r_resume = jarvis_agent.process(db=db_session, message="Resume playing.")
        assert r_resume["actions"][0]["tool_name"] == "youtube_resume"
        assert "resuming" in r_resume["response"].lower()

        # Next / Skip
        r_skip = jarvis_agent.process(db=db_session, message="Skip this song.")
        assert r_skip["actions"][0]["tool_name"] == "youtube_next"
        assert "skipped" in r_skip["response"].lower()

        # Previous
        r_prev = jarvis_agent.process(db=db_session, message="Play the previous song.")
        assert r_prev["actions"][0]["tool_name"] == "youtube_previous"
        assert "returned" in r_prev["response"].lower()

        # Stop
        r_stop = jarvis_agent.process(db=db_session, message="Stop the music.")
        assert r_stop["actions"][0]["tool_name"] == "youtube_stop"
        assert "stopped" in r_stop["response"].lower()


def test_05_nl_youtube_search_command(db_session):
    """Verify 'Search YouTube for relaxing music' routes to youtube_search_music."""
    mock_search_res = [
        {"title": "Relaxing Music 24/7", "channel": "Relax Cafe", "url": "https://www.youtube.com/watch?v=1"},
        {"title": "Deep Sleep Meditation", "channel": "Calm Channel", "url": "https://www.youtube.com/watch?v=2"}
    ]

    with patch.object(youtube_service, "search_music", return_value=mock_search_res):
        res = jarvis_agent.process(db=db_session, message="Search YouTube for relaxing music.")
        assert res["intent"] == "MUSIC_SEARCH"
        assert res["actions"][0]["tool_name"] == "youtube_search_music"
        assert "found 2 results" in res["response"].lower()


# ==================== 3. TRACK RESOLUTION & CANDIDATE SCORING ====================

def test_06_fuzzy_track_resolution_september_ends():
    """Verify 'September Ends by Green Day' resolves to 'Wake Me Up When September Ends'."""
    candidates = [
        {
            "video_id": "NU9JoFKbqZ0",
            "title": "Green Day - Wake Me Up When September Ends [Official Music Video]",
            "channel": "Green Day",
            "url": "https://www.youtube.com/watch?v=NU9JoFKbqZ0",
            "is_official": True
        },
        {
            "video_id": "other1",
            "title": "September - Earth, Wind & Fire (Cover)",
            "channel": "Random Singer",
            "url": "https://www.youtube.com/watch?v=other1",
            "is_official": False
        }
    ]

    with patch.object(youtube_service, "search_music", return_value=candidates):
        status, best, cands = youtube_service.resolve_track("September Ends", artist="Green Day")
        assert best is not None
        assert best["video_id"] == "NU9JoFKbqZ0"
        assert "Wake Me Up When September Ends" in best["title"]
        assert status in ["EXACT_MATCH", "APPROXIMATE_MATCH"]


def test_07_candidate_scoring_penalizes_covers_and_reactions():
    """Verify official video is scored higher than covers and reactions."""
    official = {
        "video_id": "vid_official",
        "title": "Linkin Park - Numb (Official Music Video)",
        "channel": "Linkin Park",
        "url": "https://www.youtube.com/watch?v=vid_official",
        "is_official": True
    }
    cover = {
        "video_id": "vid_cover",
        "title": "Numb - Linkin Park (Acoustic Cover by John)",
        "channel": "John Music",
        "url": "https://www.youtube.com/watch?v=vid_cover",
        "is_official": False
    }
    reaction = {
        "video_id": "vid_reaction",
        "title": "Vocal Coach Reacts to Linkin Park Numb",
        "channel": "Reaction Central",
        "url": "https://www.youtube.com/watch?v=vid_reaction",
        "is_official": False
    }

    score_off = youtube_service._score_candidate(official, "Numb", "Linkin Park")
    score_cov = youtube_service._score_candidate(cover, "Numb", "Linkin Park")
    score_rec = youtube_service._score_candidate(reaction, "Numb", "Linkin Park")

    assert score_off > score_cov
    assert score_off > score_rec


def test_08_ambiguous_results_handling(db_session):
    """When candidates are equally ambiguous, ask user for clarification."""
    mock_candidates = [
        {
            "video_id": "id1",
            "title": "Song Alpha by Artist One",
            "channel": "Artist One",
            "url": "https://www.youtube.com/watch?v=id1"
        },
        {
            "video_id": "id2",
            "title": "Song Alpha by Artist Two",
            "channel": "Artist Two",
            "url": "https://www.youtube.com/watch?v=id2"
        }
    ]

    with patch.object(youtube_service, "play", return_value={"status": "AMBIGUOUS_RESULT", "message": "Found multiple potential matches. Which one would you like?", "candidates": ["Song Alpha by Artist One", "Song Alpha by Artist Two"], "verified": False}):
        res = jarvis_agent.process(db=db_session, message="Play Song Alpha")
        assert "found multiple potential matches" in res["response"].lower() or "which one" in res["response"].lower()


# ==================== 4. BROWSER AUTOMATION & PLAYBACK VERIFICATION ====================

def test_09_playback_verification_failure_honest_report(db_session):
    """When video playback cannot be verified by browser, report truthful unverified status."""
    mock_play_unverified = {
        "status": "PLAYBACK_NOT_VERIFIED",
        "message": "Opened video but playback could not be verified automatically.",
        "verified": False,
        "resolved_track": "Wake Me Up When September Ends",
        "resolved_artist": "Green Day"
    }

    with patch.object(youtube_service, "play", return_value=mock_play_unverified):
        res = jarvis_agent.process(db=db_session, message="Play Wake Me Up When September Ends by Green Day")
        assert res["verified"] is False
        assert "could not be verified" in res["response"].lower()


def test_10_browser_unavailable_honest_report(db_session):
    """When controlled browser is unavailable, report truthful diagnostic."""
    mock_unavailable = {
        "status": "BROWSER_UNAVAILABLE",
        "message": "Controlled browser automation session is currently unavailable.",
        "verified": False
    }

    with patch.object(youtube_service, "play", return_value=mock_unavailable):
        res = jarvis_agent.process(db=db_session, message="Play Boulevard of Broken Dreams by Green Day")
        assert res["verified"] is False
        assert "browser" in res["response"].lower()


def test_11_composite_open_youtube_and_play_requested_song(db_session):
    """Verify 'Open YouTube and play my requested song' produces safe valid plan."""
    mock_play_res = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing on YouTube.",
        "verified": True,
        "resolved_track": "September Ends",
        "resolved_artist": "Green Day",
        "url": "https://www.youtube.com/watch?v=NU9JoFKbqZ0"
    }

    with patch.object(youtube_service, "play", return_value=mock_play_res):
        res = jarvis_agent.process(db=db_session, message="Open YouTube and play September Ends by Green Day")
        assert res["intent"] in ["MULTI_STEP_COMMAND", "MUSIC_PLAY"]
        tool_names = [a.get("tool_name") for a in res.get("actions", [])]
        assert "youtube_play" in tool_names or "local_open_url" in tool_names or "browser_navigate" in tool_names


# ==================== 5. SPOTIFY INTEGRATION PRESERVED AS OPTIONAL ====================

def test_12_explicit_spotify_command_routes_to_spotify_even_when_youtube_is_default(db_session):
    """When the user explicitly asks for Spotify, route to Spotify without breaking YouTube default."""
    mock_cand = {
        "id": "trk_02",
        "name": "Rock Anthem",
        "artist": "Various Artists",
        "album": "Rock Hits",
        "uri": "spotify:track:trk_02"
    }
    mock_play = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing Rock Anthem on Spotify",
        "verified": True,
        "track": "Rock Anthem",
        "artist": "Various Artists"
    }

    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "search_catalog", return_value=[mock_cand]), \
         patch.object(spotify_service, "play", return_value=mock_play):

        res = jarvis_agent.process(db=db_session, message="Open Spotify and play some rock music")
        assert res["intent"] == "MULTI_STEP_COMMAND"
        assert res["plan"][0]["tool_name"] == "local_open_application"
        assert res["plan"][1]["tool_name"] == "spotify_play"


def test_13_config_override_to_spotify_routes_to_spotify(db_session):
    """When MUSIC_PROVIDER=spotify is configured, route generic music commands to Spotify."""
    mock_cand = {
        "id": "trk_01",
        "name": "Holiday",
        "artist": "Green Day",
        "album": "American Idiot",
        "uri": "spotify:track:trk_01"
    }
    mock_play = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing Holiday on Spotify",
        "verified": True,
        "track": "Holiday",
        "artist": "Green Day"
    }

    with patch.object(settings, "MUSIC_PROVIDER", "spotify"), \
         patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "resolve_track", return_value=(mock_cand, "EXACT_MATCH", [mock_cand])), \
         patch.object(spotify_service, "play", return_value=mock_play):

        res = jarvis_agent.process(db=db_session, message="Play Holiday by Green Day")
        assert res["actions"][0]["tool_name"] == "spotify_play"
        assert res["verified"] is True


# ==================== 6. YOUTUBE MUSIC REGRESSION & RESILIENCE TESTS ====================

def test_14_query_variations_september_ends():
    """Verify regression queries: 'When September Ends', 'Wake Me Up When September Ends', and with artist."""
    official = {
        "title": "Green Day - Wake Me Up When September Ends [Official Music Video]",
        "video_id": "NU9JoFKlaZ0",
        "url": "https://www.youtube.com/watch?v=NU9JoFKlaZ0",
        "channel": "Green Day",
        "is_official": True
    }
    cover = {
        "title": "When September Ends - Acoustic Cover",
        "video_id": "cov1",
        "url": "https://www.youtube.com/watch?v=cov1",
        "channel": "Acoustic Singer",
        "is_official": False
    }
    candidates = [cover, official]

    queries = [
        ("When September Ends", None),
        ("Wake Me Up When September Ends", None),
        ("Wake Me Up When September Ends by Green Day", None),
        ("Wake Me Up When September Ends", "Green Day")
    ]

    with patch.object(youtube_service, "search_music", return_value=candidates):
        for q, art in queries:
            status, selected, _ = youtube_service.resolve_track(q, artist=art)
            assert selected is not None, f"Failed resolving '{q}'"
            assert selected["video_id"] == "NU9JoFKlaZ0"
            assert status == "EXACT_MATCH"


def test_15_candidate_scoring_penalizes_covers_and_tutorials():
    """Verify official video beats covers, reactions, karaoke, and tutorials."""
    official = {
        "title": "Green Day - Wake Me Up When September Ends (Official Music Video)",
        "video_id": "vid_off",
        "channel": "Green Day",
        "is_official": True
    }
    cover = {
        "title": "Wake Me Up When September Ends (Acoustic Cover)",
        "video_id": "vid_cov",
        "channel": "Singer Guy",
        "is_official": False
    }
    reaction = {
        "title": "Vocal Coach Reacts to Wake Me Up When September Ends",
        "video_id": "vid_rec",
        "channel": "Reaction Guy",
        "is_official": False
    }
    karaoke = {
        "title": "Wake Me Up When September Ends - Karaoke with Lyrics",
        "video_id": "vid_kar",
        "channel": "Sing King",
        "is_official": False
    }
    tutorial = {
        "title": "How to play Wake Me Up When September Ends Guitar Tutorial Lesson",
        "video_id": "vid_tut",
        "channel": "Guitar Lessons",
        "is_official": False
    }

    s_off = youtube_service._score_candidate(official, "Wake Me Up When September Ends", "Green Day")
    s_cov = youtube_service._score_candidate(cover, "Wake Me Up When September Ends", "Green Day")
    s_rec = youtube_service._score_candidate(reaction, "Wake Me Up When September Ends", "Green Day")
    s_kar = youtube_service._score_candidate(karaoke, "Wake Me Up When September Ends", "Green Day")
    s_tut = youtube_service._score_candidate(tutorial, "Wake Me Up When September Ends", "Green Day")

    assert s_off > s_cov
    assert s_off > s_rec
    assert s_off > s_kar
    assert s_off > s_tut


def test_16_distinguish_empty_results_from_errors():
    """Verify that a genuine no-match is cleanly distinguished from browser, session, and network errors."""
    # 1. Genuine empty search results
    with patch.object(youtube_service, "search_music", return_value=[]):
        res_empty = youtube_service.play(track="Nonexistent Obscure Track 12345XYZ")
        assert res_empty["status"] == "TRACK_NOT_FOUND"
        assert "could not find" in res_empty["message"].lower()

    # 2. Browser unavailable
    with patch.object(youtube_service, "search_music", side_effect=BrowserUnavailableError("Edge not found")):
        res_bue = youtube_service.play(track="When September Ends")
        assert res_bue["status"] == "BROWSER_UNAVAILABLE"
        assert "browser unavailable" in res_bue["message"].lower()

    # 3. Session closed
    with patch.object(youtube_service, "search_music", side_effect=NoActivePageError("Browser session closed")):
        res_nape = youtube_service.play(track="When September Ends")
        assert res_nape["status"] == "SESSION_CLOSED"
        assert "closed" in res_nape["message"].lower()

    # 4. Network error during search
    with patch.object(youtube_service, "search_music", side_effect=YouTubeMusicServiceError("DNS failure", code="NETWORK_ERROR")):
        res_net = youtube_service.play(track="When September Ends")
        assert res_net["status"] == "NETWORK_ERROR"

    # 5. Extraction error during search
    with patch.object(youtube_service, "search_music", side_effect=YouTubeMusicServiceError("DOM changed", code="EXTRACTION_ERROR")):
        res_ext = youtube_service.play(track="When September Ends")
        assert res_ext["status"] == "EXTRACTION_ERROR"

    # 6. Navigation security blocked
    with patch.object(youtube_service, "search_music", side_effect=BrowserSecurityError("Blocked IP")):
        res_sec = youtube_service.play(track="When September Ends")
        assert res_sec["status"] == "SECURITY_BLOCKED"


def test_17_successful_match_passes_selected_url_and_video_id_to_playback():
    """Verify that resolving a track forwards the selected canonical URL and video ID to the player."""
    match_cand = {
        "title": "Green Day - Wake Me Up When September Ends [Official Music Video]",
        "video_id": "NU9JoFKlaZ0",
        "url": "https://www.youtube.com/watch?v=NU9JoFKlaZ0",
        "channel": "Green Day",
        "is_official": True
    }

    mock_state = {
        "player_found": True,
        "paused": False,
        "currentTime": 8.5,
        "duration": 285.0,
        "title": match_cand["title"],
        "channel": match_cand["channel"]
    }

    mock_sess = MagicMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_sess.page = mock_page

    def _fake_play_run(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return mock_state

    with patch.object(youtube_service, "resolve_track", return_value=("EXACT_MATCH", match_cand, [match_cand])), \
         patch("app.services.youtube_service.browser_automation_service._get_active_session", return_value=mock_sess), \
         patch("app.services.youtube_service.browser_worker.run_coro", side_effect=_fake_play_run):

        res = youtube_service.play(track="When September Ends")

        assert res["status"] == "PLAYBACK_CONFIRMED"
        assert res["verified"] is True
        assert res["url"] == "https://www.youtube.com/watch?v=NU9JoFKlaZ0"
        assert res["video_id"] == "NU9JoFKlaZ0"
        assert res["track"] == match_cand["title"]
        assert res["artist"] == match_cand["channel"]


def test_18_planner_does_not_unnecessarily_open_youtube_before_playback():
    """Verify that requests to play music route directly to youtube_play without a redundant local_open_url step."""
    planner = AgentPlanner()

    test_queries = [
        "play When September Ends",
        "play Wake Me Up When September Ends",
        "play Wake Me Up When September Ends by Green Day",
        "Open YouTube and play When September Ends",
        "Open YouTube and play September Ends by Green Day",
        "play When September Ends on YouTube"
    ]

    for q in test_queries:
        res = intent_detector.detect(q)
        plan = planner.create_plan(res, AgentContext(user_message=q, intent=res.intent))

        tool_names = [s.tool_name or s.tool for s in plan.steps]
        # Must execute youtube_play directly
        assert "youtube_play" in tool_names, f"Query '{q}' did not include youtube_play"
        # Must NOT include local_open_url
        assert "local_open_url" not in tool_names, f"Query '{q}' included redundant local_open_url: {tool_names}"
        assert len(plan.steps) == 1, f"Expected single-step plan for '{q}', got {len(plan.steps)} steps"


def test_19_mocked_playwright_resilient_dom_extraction():
    """Deterministic unit test verifying search_music Playwright page orchestration and evaluation with mocks."""
    mock_sess = MagicMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_sess.page = mock_page

    raw_candidates = [
        {
            "title": "Green Day - Wake Me Up When September Ends",
            "video_id": "NU9JoFKlaZ0",
            "url": "https://www.youtube.com/watch?v=NU9JoFKlaZ0",
            "channel": "Green Day",
            "is_official": True
        }
    ]

    def _fake_search_run(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return raw_candidates

    with patch("app.services.youtube_service.browser_automation_service._get_active_session", return_value=mock_sess), \
         patch("app.services.youtube_service.browser_worker.run_coro", side_effect=_fake_search_run):

        results = youtube_service.search_music("When September Ends", limit=5)

        assert len(results) == 1
        assert results[0]["video_id"] == "NU9JoFKlaZ0"


def test_20_e2e_jarvis_agent_play_when_september_ends(db_session):
    """End-to-end regression test for 'play When September Ends' verifying full pipeline and truthful playback response."""
    match_cand = {
        "title": "Green Day - Wake Me Up When September Ends [Official Music Video]",
        "video_id": "NU9JoFKlaZ0",
        "url": "https://www.youtube.com/watch?v=NU9JoFKlaZ0",
        "channel": "Green Day",
        "is_official": True
    }
    mock_state = {
        "player_found": True,
        "paused": False,
        "currentTime": 5.0,
        "duration": 285.0,
        "title": match_cand["title"],
        "channel": match_cand["channel"]
    }

    mock_sess = MagicMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_sess.page = mock_page

    def _fake_play_run(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return mock_state

    with patch.object(youtube_service, "resolve_track", return_value=("EXACT_MATCH", match_cand, [match_cand])), \
         patch("app.services.youtube_service.browser_automation_service._get_active_session", return_value=mock_sess), \
         patch("app.services.youtube_service.browser_worker.run_coro", side_effect=_fake_play_run):

        res = jarvis_agent.process(db=db_session, message="play When September Ends")

        assert res["intent"] == "MUSIC_PLAY"
        assert res["verified"] is True
        assert len(res["actions"]) == 1
        assert res["actions"][0]["tool_name"] == "youtube_play"

        out = res["actions"][0]["output"]
        assert out["status"] == "PLAYBACK_CONFIRMED"
        assert out["video_id"] == "NU9JoFKlaZ0"
        assert out["url"] == "https://www.youtube.com/watch?v=NU9JoFKlaZ0"

        # Verify response text incorporates resolved track, artist, and provider truthfully
        resp_low = res["response"].lower()
        assert "wake me up when september ends" in resp_low
        assert "green day" in resp_low
        assert "youtube" in resp_low
        assert "could not find" not in resp_low


def test_21_e2e_jarvis_agent_open_youtube_and_play_when_september_ends(db_session):
    """End-to-end regression test for composite 'Open YouTube and play When September Ends'."""
    match_cand = {
        "title": "Green Day - Wake Me Up When September Ends [Official Music Video]",
        "video_id": "NU9JoFKlaZ0",
        "url": "https://www.youtube.com/watch?v=NU9JoFKlaZ0",
        "channel": "Green Day",
        "is_official": True
    }
    mock_state = {
        "player_found": True,
        "paused": False,
        "currentTime": 3.0,
        "duration": 285.0,
        "title": match_cand["title"],
        "channel": match_cand["channel"]
    }

    mock_sess = MagicMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_sess.page = mock_page

    def _fake_play_run(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return mock_state

    with patch.object(youtube_service, "resolve_track", return_value=("EXACT_MATCH", match_cand, [match_cand])), \
         patch("app.services.youtube_service.browser_automation_service._get_active_session", return_value=mock_sess), \
         patch("app.services.youtube_service.browser_worker.run_coro", side_effect=_fake_play_run):

        res = jarvis_agent.process(db=db_session, message="Open YouTube and play When September Ends")

        # Must not have redundant local_open_url step
        tool_names = [a["tool_name"] for a in res["actions"]]
        assert "youtube_play" in tool_names
        assert "local_open_url" not in tool_names
        assert len(res["actions"]) == 1
        assert res["verified"] is True
        assert "wake me up when september ends" in res["response"].lower()
        assert "could not find" not in res["response"].lower()


def test_22_e2e_youtube_error_statuses_do_not_leak_to_spotify_or_generic_errors(db_session):
    """End-to-end verification that specialized YouTube errors are formatted cleanly and never mention Spotify."""
    error_cases = [
        ({"status": "NETWORK_ERROR", "service": "youtube", "message": "YouTube search navigation failed: DNS timeout", "verified": False}, "network error"),
        ({"status": "SESSION_CLOSED", "service": "youtube", "message": "Browser session closed: session terminated", "verified": False}, "session closed"),
        ({"status": "PROVIDER_ERROR", "service": "youtube", "message": "YouTube playback failed: video unavailable in your country", "verified": False}, "failed"),
        ({"status": "SECURITY_BLOCKED", "service": "youtube", "message": "Navigation blocked: URL forbidden", "verified": False}, "blocked"),
        ({"status": "TRACK_NOT_FOUND", "service": "youtube", "message": "Could not find 'NonexistentXYZ' on YouTube.", "verified": False}, "could not find")
    ]

    for mock_err, expected_phrase in error_cases:
        with patch.object(youtube_service, "play", return_value=mock_err):
            res = jarvis_agent.process(db=db_session, message="play When September Ends")
            assert res["verified"] is False
            resp_low = res["response"].lower()
            assert "spotify" not in resp_low
            assert expected_phrase in resp_low or mock_err["message"].lower() in resp_low


def test_23_youtube_service_returns_consistent_track_artist_aliases():
    """Verify that youtube_service.play returns consistent track, title, resolved_track, artist, and channel aliases."""
    match_cand = {
        "title": "Green Day - Wake Me Up When September Ends",
        "video_id": "NU9JoFKlaZ0",
        "url": "https://www.youtube.com/watch?v=NU9JoFKlaZ0",
        "channel": "Green Day",
        "is_official": True
    }
    mock_state = {
        "player_found": True,
        "paused": False,
        "currentTime": 10.0,
        "duration": 285.0,
        "title": match_cand["title"],
        "channel": match_cand["channel"]
    }

    mock_sess = MagicMock()
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_sess.page = mock_page

    def _fake_play_run(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return mock_state

    with patch.object(youtube_service, "resolve_track", return_value=("EXACT_MATCH", match_cand, [match_cand])), \
         patch("app.services.youtube_service.browser_automation_service._get_active_session", return_value=mock_sess), \
         patch("app.services.youtube_service.browser_worker.run_coro", side_effect=_fake_play_run):

        out = youtube_service.play(track="When September Ends")

        assert out["status"] == "PLAYBACK_CONFIRMED"
        assert out["track"] == match_cand["title"]
        assert out["title"] == match_cand["title"]
        assert out["resolved_track"] == match_cand["title"]
        assert out["artist"] == match_cand["channel"]
        assert out["channel"] == match_cand["channel"]
        assert out["resolved_artist"] == match_cand["channel"]
        assert out["video_id"] == "NU9JoFKlaZ0"
        assert out["url"] == "https://www.youtube.com/watch?v=NU9JoFKlaZ0"


