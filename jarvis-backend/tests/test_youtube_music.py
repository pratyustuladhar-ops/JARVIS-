import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.ai.agent import jarvis_agent
from app.ai.intent import intent_detector
from app.services.youtube_service import youtube_service
from app.services.spotify_service import spotify_service
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
