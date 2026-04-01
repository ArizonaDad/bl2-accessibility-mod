"""
TTS Engine for BL2 Accessibility Mod.
Uses Windows SAPI (Speech API) via comtypes for text-to-speech.
Falls back to ctypes SAPI COM if comtypes unavailable.
"""

import threading
import queue
from typing import Optional

# Try comtypes first, then fall back to a simpler approach
_engine = None
_speech_queue: queue.Queue = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_running = False
_rate = 3  # -10 to 10, default 0, we go faster for gaming
_volume = 100  # 0-100


def _worker():
    """Background thread that processes TTS queue using SAPI."""
    global _engine, _running
    try:
        import comtypes.client
        _engine = comtypes.client.CreateObject("SAPI.SpVoice")
        _engine.Rate = _rate
        _engine.Volume = _volume
    except Exception:
        # Fallback: use win32com if available
        try:
            import win32com.client
            _engine = win32com.client.Dispatch("SAPI.SpVoice")
            _engine.Rate = _rate
            _engine.Volume = _volume
        except Exception:
            # Last resort: try pyttsx3
            try:
                import pyttsx3
                _engine = pyttsx3.init()
                _engine.setProperty('rate', 200 + (_rate * 20))
                _engine.setProperty('volume', _volume / 100.0)
            except Exception:
                _engine = None

    while _running:
        try:
            text, interrupt = _speech_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if _engine is None:
            continue

        try:
            if interrupt:
                # SVSFlagsAsync = 1, SVSFPurgeBeforeSpeak = 2
                _engine.Speak(text, 1 | 2)
            else:
                # SVSFlagsAsync = 1
                _engine.Speak(text, 1)
        except Exception:
            pass


def init():
    """Initialize the TTS system. Call once at mod startup."""
    global _worker_thread, _running
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _running = True
    _worker_thread = threading.Thread(target=_worker, daemon=True, name="BL2A11y-TTS")
    _worker_thread.start()


def shutdown():
    """Shut down the TTS system."""
    global _running
    _running = False
    if _worker_thread is not None:
        _worker_thread.join(timeout=2.0)


def speak(text: str, interrupt: bool = True):
    """
    Speak text via TTS.

    Args:
        text: The text to speak.
        interrupt: If True, cancel any currently speaking text first.
    """
    if not text:
        return
    if interrupt:
        # Clear the queue
        while not _speech_queue.empty():
            try:
                _speech_queue.get_nowait()
            except queue.Empty:
                break
    _speech_queue.put((text, interrupt))


def stop():
    """Stop any currently playing speech."""
    # Clear queue
    while not _speech_queue.empty():
        try:
            _speech_queue.get_nowait()
        except queue.Empty:
            break
    # Speak empty string with purge to stop current speech
    _speech_queue.put(("", True))


def set_rate(rate: int):
    """Set speech rate (-10 to 10)."""
    global _rate
    _rate = max(-10, min(10, rate))
    if _engine is not None:
        try:
            _engine.Rate = _rate
        except Exception:
            pass


def set_volume(vol: int):
    """Set speech volume (0-100)."""
    global _volume
    _volume = max(0, min(100, vol))
    if _engine is not None:
        try:
            _engine.Volume = _volume
        except Exception:
            pass
