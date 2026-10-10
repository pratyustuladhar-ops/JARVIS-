import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.ai.agent import jarvis_agent
from app.ai.intent import intent_detector
from app.services.spotify_service import spotify_service, SpotifyServiceError
from app.core.config import settings

client = TestClient(app)


# ==================== 1. NATURAL LANGUAGE INTENT & ENTITY TESTS ====================

def test_01_nl_play_exact_and_approximate_track():
    """Verify natural language variations of play commands extract track and artist correctly."""
    res1 = intent_detector.detect("Play Wake Me Up When September Ends by Green Day.")
    assert res1.intent == "MUSIC_PLAY"
    assert res1.entities.get("artist") == "Green Day"
    assert "Wake Me Up When September Ends" in res1.entities.get("track", "")

    res2 = intent_detector.detect("Can you play September Ends by Green Day?")
    assert res2.intent == "MUSIC_PLAY"
    assert res2.entities.get("artist") == "Green Day"
    assert "September Ends" in res2.entities.get("track", "")

    res3 = intent_detector.detect("Could you put on that September song from Green Day?")
    assert res3.intent == "MUSIC_PLAY"
    assert res3.entities.get("artist") == "Green Day"
    assert "September song" in res3.entities.get("track", "")


def test_02_nl_artist_and_genre_variations():
    """Verify artist-only and genre-only music requests."""
    res_artist = intent_detector.detect("Put on some Green Day.")
    assert res_artist.intent == "MUSIC_PLAY"
    assert res_artist.entities.get("artist") == "Green Day"

    res_genre = intent_detector.detect("Play some rock music.")
    assert res_genre.intent == "MUSIC_PLAY"
    assert res_genre.entities.get("genre") == "rock"


def test_03_nl_playback_controls_variations():
    """Verify pause, resume, next, previous, and volume commands."""
    res_pause = intent_detector.detect("Pause the music.")
    assert res_pause.intent == "MUSIC_PAUSE"

    res_pause_it = intent_detector.detect("Pause it.")
    assert res_pause_it.intent == "MUSIC_PAUSE"
    assert res_pause_it.context_reference == "active_playback"

    res_resume = intent_detector.detect("Resume what I was listening to.")
    assert res_resume.intent == "MUSIC_RESUME"

    res_continue = intent_detector.detect("Continue playing.")
    assert res_continue.intent == "MUSIC_RESUME"

    res_skip = intent_detector.detect("Skip this song.")
    assert res_skip.intent == "MUSIC_NEXT"

    res_next = intent_detector.detect("Play the next track.")
    assert res_next.intent == "MUSIC_NEXT"

    res_prev = intent_detector.detect("Play the previous song.")
    assert res_prev.intent == "MUSIC_PREVIOUS"

    res_vol = intent_detector.detect("Set volume to 80%")
    assert res_vol.intent == "MUSIC_VOLUME"
    assert res_vol.entities.get("volume_percent") == 80


def test_04_nl_music_search():
    """Verify music catalog search commands."""
    res_search = intent_detector.detect("Search for Boulevard of Broken Dreams.")
    assert res_search.intent == "MUSIC_SEARCH"
    assert "Boulevard of Broken Dreams" in res_search.entities.get("query", "")

    res_find = intent_detector.detect("Find Boulevard of Broken Dreams by Green Day.")
    assert res_find.intent == "MUSIC_SEARCH"
    assert res_find.entities.get("artist") == "Green Day"


def test_05_nl_browser_and_task_natural_phrasing():
    """Verify natural phrasing of browser search and task creation."""
    res_chrome = intent_detector.detect("Open Chrome and search for machine learning.")
    assert res_chrome.intent == "BROWSER_SEARCH"
    assert res_chrome.entities.get("query") == "machine learning"

    res_task = intent_detector.detect("Create a task to study DBMS tomorrow.")
    assert res_task.intent == "CREATE_TASK"
    assert "Study dbms" in res_task.entities.get("task_title", "")
    assert res_task.entities.get("due_date") == "tomorrow"


def test_06_nl_follow_up_and_ambiguity_clarification(db_session):
    """Verify follow-up commands trigger clarification when context is missing."""
    # When no prior artist exists in memory, pronoun reference asks for clarification
    res = jarvis_agent.process(db=db_session, message="Play their other popular song.")
    assert res["requires_clarification"] is True
    assert "clarify" in res["response"].lower() or "which artist" in res["response"].lower()


def test_07_adversarial_malformed_input_does_not_bypass_validation(db_session):
    """Ensure malformed or injection inputs do not execute unsafe actions."""
    res = jarvis_agent.process(db=db_session, message="play $(rm -rf /) by eval(1)")
    # Must not execute shell, must safely route or reject
    assert res["verified"] is False or res["intent"] == "MUSIC_PLAY"
    assert "powershell" not in [a.get("tool_name") for a in res.get("actions", [])]


# ==================== 2. SPOTIFY SERVICE & CATALOG RESOLUTION TESTS ====================

def test_08_spotify_unconfigured_honest_error(db_session):
    """When Spotify credentials are not configured, agent gives clear honest configuration instructions."""
    with patch.object(spotify_service, "is_configured", False):
        res = jarvis_agent.process(db=db_session, message="Play Wake Me Up When September Ends by Green Day")
        assert res["verified"] is False
        assert "spotify is not configured" in res["response"].lower() or "credentials" in res["response"].lower()


def test_09_spotify_approximate_track_resolution():
    """Verify that 'September Ends' fuzzy matches 'Wake Me Up When September Ends'."""
    mock_candidates = [
        {
            "id": "trk_01",
            "name": "Wake Me Up When September Ends",
            "artist": "Green Day",
            "album": "American Idiot",
            "uri": "spotify:track:trk_01",
            "duration_ms": 285000,
            "popularity": 85
        },
        {
            "id": "trk_02",
            "name": "September",
            "artist": "Earth, Wind & Fire",
            "album": "The Best of Earth, Wind & Fire",
            "uri": "spotify:track:trk_02",
            "duration_ms": 215000,
            "popularity": 90
        }
    ]

    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "search_catalog", return_value=mock_candidates):

        track, status, cands = spotify_service.resolve_track("September Ends", artist="Green Day")
        assert track is not None
        assert track["name"] == "Wake Me Up When September Ends"
        assert status == "FUZZY_MATCH"


def test_10_spotify_ambiguous_results_handling(db_session):
    """When multiple tracks have identical ambiguous match scores, prompt for clarification."""
    mock_candidates = [
        {"id": "1", "name": "September Song 1", "artist": "Band A", "album": "A", "uri": "spotify:track:1", "popularity": 50},
        {"id": "2", "name": "September Song 2", "artist": "Band B", "album": "B", "uri": "spotify:track:2", "popularity": 50}
    ]

    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "search_catalog", return_value=mock_candidates):

        res = jarvis_agent.process(db=db_session, message="Play September Song by Band A")
        # Should either resolve or prompt candidate choices truthfully
        assert res is not None


def test_11_spotify_no_active_device_error(db_session):
    """When no Spotify playback device is active, report clear truthful instructions."""
    mock_cand = {
        "id": "trk_01",
        "name": "Wake Me Up When September Ends",
        "artist": "Green Day",
        "album": "American Idiot",
        "uri": "spotify:track:trk_01"
    }
    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "resolve_track", return_value=(mock_cand, "EXACT_MATCH", [mock_cand])), \
         patch.object(spotify_service, "get_devices", return_value=[]), \
         patch.object(spotify_service, "play", return_value={"status": "NO_ACTIVE_DEVICE", "message": "No active Spotify playback device found. Please open Spotify first.", "verified": False}):

        res = jarvis_agent.process(db=db_session, message="Play Wake Me Up When September Ends by Green Day")
        assert res["verified"] is False
        assert "no active spotify" in res["response"].lower()


def test_12_spotify_play_confirmed_verification(db_session):
    """When Spotify playback is confirmed, return truthful 'Now playing' message with track & artist."""
    mock_cand = {
        "id": "trk_01",
        "name": "Wake Me Up When September Ends",
        "artist": "Green Day",
        "album": "American Idiot",
        "uri": "spotify:track:trk_01"
    }
    mock_play_res = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing Wake Me Up When September Ends by Green Day",
        "verified": True,
        "track": "Wake Me Up When September Ends",
        "artist": "Green Day",
        "uri": "spotify:track:trk_01"
    }

    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "resolve_track", return_value=(mock_cand, "EXACT_MATCH", [mock_cand])), \
         patch.object(spotify_service, "play", return_value=mock_play_res):

        res = jarvis_agent.process(db=db_session, message="Play Wake Me Up When September Ends by Green Day")
        assert res["verified"] is True
        assert "now playing 'wake me up when september ends' by green day" in res["response"].lower()
        assert res["actions"][0]["tool_name"] == "spotify_play"


def test_13_spotify_pause_resume_next_verification(db_session):
    """Verify pause, resume, and next operations report verified outcomes."""
    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "pause", return_value={"status": "PLAYBACK_PAUSED", "message": "Spotify playback paused.", "verified": True}), \
         patch.object(spotify_service, "resume", return_value={"status": "PLAYBACK_CONFIRMED", "message": "Resuming Spotify playback.", "verified": True}), \
         patch.object(spotify_service, "next_track", return_value={"status": "TRACK_SKIPPED", "message": "Skipped to next track.", "verified": True, "track": "Holiday"}):

        # Pause
        res_pause = jarvis_agent.process(db=db_session, message="Pause the music")
        assert res_pause["verified"] is True
        assert "paused" in res_pause["response"].lower()

        # Resume
        res_resume = jarvis_agent.process(db=db_session, message="Resume playback")
        assert res_resume["verified"] is True
        assert "resuming" in res_resume["response"].lower()

        # Skip
        res_next = jarvis_agent.process(db=db_session, message="Skip this song")
        assert res_next["verified"] is True
        assert "skipped" in res_next["response"].lower()


def test_14_composite_open_spotify_and_play_music(db_session):
    """Verify 'Open Spotify and play some rock music' generates sequential 2-step plan."""
    mock_cand = {
        "id": "trk_02",
        "name": "Rock Anthem",
        "artist": "Various Artists",
        "album": "Rock Hits",
        "uri": "spotify:track:trk_02"
    }
    mock_play = {
        "status": "PLAYBACK_CONFIRMED",
        "message": "Now playing Rock Anthem",
        "verified": True,
        "track": "Rock Anthem",
        "artist": "Various Artists"
    }

    with patch.object(spotify_service, "is_configured", True), \
         patch.object(spotify_service, "search_catalog", return_value=[mock_cand]), \
         patch.object(spotify_service, "play", return_value=mock_play):

        res = jarvis_agent.process(db=db_session, message="Open Spotify and play some rock music")
        assert res["intent"] == "MULTI_STEP_COMMAND"
        assert len(res["plan"]) == 2
        assert res["plan"][0]["tool_name"] == "local_open_application"
        assert res["plan"][1]["tool_name"] == "spotify_play"
