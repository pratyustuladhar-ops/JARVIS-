"""
Microphone Audio Capture Stream for JARVIS Windows Local Agent.
Provides continuous, low-latency audio capture via PyAudio with bounded queueing,
exponential backoff on device disconnection, acoustic echo pause/resume, and clean shutdown.
"""

import os
import time
import queue
import logging
import threading
from typing import Optional, Generator, Tuple
import numpy as np

logger = logging.getLogger("jarvis.local_agent.audio_capture")

# Standard audio format for local speech processing and openWakeWord
SAMPLE_RATE = 16000  # 16 kHz
CHANNELS = 1         # Mono
SAMPLE_WIDTH = 2     # 16-bit signed integer (paInt16)
CHUNK_SIZE = 1280    # 80ms chunk at 16kHz
QUEUE_MAX_SIZE = 35  # Max ~2.8 seconds buffer; drops older frames under load to prevent memory leak


class AudioStreamState:
    UNINITIALIZED = "UNINITIALIZED"
    STARTING = "STARTING"
    LISTENING = "LISTENING"
    PAUSED = "PAUSED"
    NO_MICROPHONE = "NO_MICROPHONE"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class MicrophoneStream:
    """
    Thread-safe microphone capture stream.
    Streams 16-bit PCM mono audio chunks from PyAudio into a bounded queue.
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        chunk_size: int = CHUNK_SIZE,
        device_index: Optional[int] = None,
        max_queue_size: int = QUEUE_MAX_SIZE
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        env_dev = os.getenv("JARVIS_MIC_DEVICE_INDEX")
        self.device_index = int(env_dev) if env_dev is not None and env_dev.isdigit() else device_index
        self.max_queue_size = max_queue_size

        self.state = AudioStreamState.UNINITIALIZED
        self.last_error: Optional[str] = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=self.max_queue_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
        self._pyaudio_instance = None
        self._active_stream = None

    def get_state(self) -> str:
        with self._lock:
            return self.state

    def get_last_error(self) -> Optional[str]:
        with self._lock:
            return self.last_error

    def start(self) -> bool:
        """Starts background microphone streaming thread."""
        with self._lock:
            if self._capture_thread and self._capture_thread.is_alive():
                return True
            self._stop_event.clear()
            self._pause_event.clear()
            self.state = AudioStreamState.STARTING
            self._capture_thread = threading.Thread(
                target=self._run_capture_loop,
                name="JarvisMicCaptureThread",
                daemon=True
            )
            self._capture_thread.start()
            return True

    def stop(self) -> None:
        """Stops the audio capture thread and releases audio device."""
        self._stop_event.set()
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)
        self._cleanup_audio_device()
        with self._lock:
            self.state = AudioStreamState.STOPPED

    def pause(self) -> None:
        """Pauses audio streaming (e.g. during TTS vocalization)."""
        self._pause_event.set()
        with self._lock:
            if self.state == AudioStreamState.LISTENING:
                self.state = AudioStreamState.PAUSED
        # Clear backlog queue to avoid processing stale frames on resume
        self._clear_queue()

    def resume(self) -> None:
        """Resumes audio streaming after speech playback."""
        self._clear_queue()
        self._pause_event.clear()
        with self._lock:
            if self.state == AudioStreamState.PAUSED:
                self.state = AudioStreamState.LISTENING

    def read_frame(self, timeout: float = 0.2) -> Optional[np.ndarray]:
        """
        Reads one audio frame (numpy int16 array of size CHUNK_SIZE).
        Returns None on timeout or if paused/stopped.
        """
        if self._pause_event.is_set():
            return None
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _clear_queue(self):
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def _init_audio_device(self) -> bool:
        try:
            import pyaudio
        except ImportError:
            with self._lock:
                self.last_error = "PyAudio library not installed."
                self.state = AudioStreamState.ERROR
            logger.error(self.last_error)
            return False

        try:
            if not self._pyaudio_instance:
                self._pyaudio_instance = pyaudio.PyAudio()

            # Verify input device availability
            count = self._pyaudio_instance.get_device_count()
            if count == 0:
                with self._lock:
                    self.last_error = "No audio devices detected on this system."
                    self.state = AudioStreamState.NO_MICROPHONE
                return False

            dev_index = self.device_index
            if dev_index is not None:
                try:
                    dev_info = self._pyaudio_instance.get_device_info_by_index(dev_index)
                    if dev_info.get("maxInputChannels", 0) <= 0:
                        dev_index = None  # Fallback to default
                except Exception:
                    dev_index = None

            # Open audio input stream
            stream_kwargs = {
                "format": pyaudio.paInt16,
                "channels": CHANNELS,
                "rate": self.sample_rate,
                "input": True,
                "frames_per_buffer": self.chunk_size,
            }
            if dev_index is not None:
                stream_kwargs["input_device_index"] = dev_index

            self._active_stream = self._pyaudio_instance.open(**stream_kwargs)
            with self._lock:
                self.state = AudioStreamState.LISTENING
                self.last_error = None
            logger.info(f"Microphone stream opened successfully (rate={self.sample_rate}, chunk={self.chunk_size})")
            return True

        except Exception as e:
            with self._lock:
                self.last_error = f"Failed to open microphone: {str(e)}"
                self.state = AudioStreamState.NO_MICROPHONE if "device" in str(e).lower() else AudioStreamState.ERROR
            logger.warning(f"Audio device open notice: {e}")
            self._cleanup_audio_device()
            return False

    def _cleanup_audio_device(self):
        if self._active_stream:
            try:
                self._active_stream.stop_stream()
                self._active_stream.close()
            except Exception:
                pass
            self._active_stream = None

        if self._pyaudio_instance:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            self._pyaudio_instance = None

    def _run_capture_loop(self):
        backoff_seconds = 1.0
        max_backoff = 10.0
        consecutive_failures = 0
        max_fast_retries = 3

        while not self._stop_event.is_set():
            if not self._active_stream:
                success = self._init_audio_device()
                if not success:
                    consecutive_failures += 1
                    with self._lock:
                        if consecutive_failures <= max_fast_retries:
                            self.state = AudioStreamState.RECONNECTING
                        elif "device" in str(self.last_error).lower() or "host error" in str(self.last_error).lower():
                            self.state = AudioStreamState.NO_MICROPHONE
                        else:
                            self.state = AudioStreamState.ERROR

                    # Bounded backoff retry
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 1.5, max_backoff)
                    continue
                else:
                    consecutive_failures = 0
                    backoff_seconds = 1.0

            if self._pause_event.is_set():
                time.sleep(0.08)
                continue

            try:
                # Read raw PCM data from PyAudio stream
                raw_data = self._active_stream.read(self.chunk_size, exception_on_overflow=False)
                if not raw_data:
                    time.sleep(0.02)
                    continue

                audio_frame = np.frombuffer(raw_data, dtype=np.int16)

                # Bounded queue: Drop oldest frame if full to prevent latency drift and memory growth
                if self._audio_queue.full():
                    try:
                        self._audio_queue.get_nowait()
                    except queue.Empty:
                        pass

                self._audio_queue.put_nowait(audio_frame)

            except Exception as e:
                logger.warning(f"Audio read error in capture loop: {e}. Reinitializing audio stream...")
                self._cleanup_audio_device()
                consecutive_failures += 1
                with self._lock:
                    self.state = AudioStreamState.RECONNECTING if consecutive_failures <= max_fast_retries else AudioStreamState.ERROR
                    self.last_error = str(e)
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 1.5, max_backoff)

        self._cleanup_audio_device()
        with self._lock:
            self.state = AudioStreamState.STOPPED
