"""
TTS Engine for BL2 Accessibility Mod.
Uses Windows SAPI via ctypes COM (no third-party dependencies).
The SDK's bundled Python 3.13 has ctypes but NOT comtypes/win32com/pyttsx3.
"""

import ctypes
import ctypes.wintypes
import threading
import queue
from typing import Optional

try:
    from unrealsdk import logging as sdk_logging
    def _log(msg):
        sdk_logging.info(f"[BL2A11y TTS] {msg}")
    def _log_error(msg):
        sdk_logging.error(f"[BL2A11y TTS] {msg}")
except Exception:
    def _log(msg):
        pass
    def _log_error(msg):
        pass

# COM constants
CLSCTX_ALL = 0x17
COINIT_MULTITHREADED = 0x0
SVSFlagsAsync = 1
SVSFPurgeBeforeSpeak = 2

# COM GUIDs
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

# SAPI SpVoice CLSID: {96749377-3391-11D2-9EE3-00C04F797396}
CLSID_SpVoice = GUID(0x96749377, 0x3391, 0x11D2,
    (ctypes.c_ubyte * 8)(0x9E, 0xE3, 0x00, 0xC0, 0x4F, 0x79, 0x73, 0x96))

# ISpVoice IID: {6C44DF74-72B9-4992-A1EC-EF996E0422D4}
IID_ISpVoice = GUID(0x6C44DF74, 0x72B9, 0x4992,
    (ctypes.c_ubyte * 8)(0xA1, 0xEC, 0xEF, 0x99, 0x6E, 0x04, 0x22, 0xD4))

_speech_queue: queue.Queue = queue.Queue()
_worker_thread: Optional[threading.Thread] = None
_running = False
_rate = 3
_volume = 100

# ISpVoice vtable offsets (from IUnknown + ISpVoice methods)
# IUnknown: QueryInterface(0), AddRef(1), Release(2)
# ISpVoice inherits from ISpEventSource inherits from ISpNotifySource inherits from IUnknown
# ISpVoice::Speak is at vtable index 20
# ISpVoice::SetRate is at vtable index 26
# ISpVoice::SetVolume is at vtable index 28
VTBL_SPEAK = 20
VTBL_SET_RATE = 26
VTBL_SET_VOLUME = 28
VTBL_RELEASE = 2


def _get_vtbl_func(this_ptr, index, restype, *argtypes):
    """Get a COM method from the vtable with proper type signature."""
    vtbl = ctypes.cast(this_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    method_ptr = vtbl[index]
    func_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return func_type(method_ptr)


def _worker():
    """Background thread that processes TTS queue using Windows SAPI COM."""
    global _running
    voice_ptr = ctypes.c_void_p()

    try:
        # Initialize COM on this thread
        ole32 = ctypes.windll.ole32
        hr = ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        _log(f"CoInitializeEx result: {hr}")

        # Create SpVoice instance
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_SpVoice),
            None,
            CLSCTX_ALL,
            ctypes.byref(IID_ISpVoice),
            ctypes.byref(voice_ptr)
        )
        _log(f"CoCreateInstance result: {hr}, voice_ptr: {voice_ptr.value}")

        if hr != 0 or voice_ptr.value is None:
            _log_error(f"Failed to create SpVoice: HRESULT={hr}")
            # Fallback: try using PowerShell for TTS
            _worker_powershell_fallback()
            return

        # Set rate: ISpVoice::SetRate(long Rate) -> HRESULT
        try:
            set_rate_fn = _get_vtbl_func(voice_ptr.value, VTBL_SET_RATE, ctypes.c_long, ctypes.c_long)
            set_rate_fn(voice_ptr.value, _rate)
        except Exception as e:
            _log_error(f"Failed to set rate: {e}")

        # Set volume: ISpVoice::SetVolume(USHORT Volume) -> HRESULT
        try:
            set_vol_fn = _get_vtbl_func(voice_ptr.value, VTBL_SET_VOLUME, ctypes.c_long, ctypes.c_ushort)
            set_vol_fn(voice_ptr.value, _volume)
        except Exception as e:
            _log_error(f"Failed to set volume: {e}")

        _log("SAPI voice initialized successfully")

        # ISpVoice::Speak(LPCWSTR pwcs, DWORD dwFlags, ULONG* pulStreamNumber) -> HRESULT
        speak_fn = _get_vtbl_func(
            voice_ptr.value, VTBL_SPEAK, ctypes.c_long,
            ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p
        )

        while _running:
            try:
                text, interrupt = _speech_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if not text:
                # Empty text with interrupt = stop current speech
                try:
                    speak_fn(voice_ptr.value, "", SVSFlagsAsync | SVSFPurgeBeforeSpeak, None)
                except Exception:
                    pass
                continue

            try:
                flags = SVSFlagsAsync
                if interrupt:
                    flags |= SVSFPurgeBeforeSpeak
                speak_fn(voice_ptr.value, text, flags, None)
            except Exception as e:
                _log_error(f"Speak failed: {e}")

    except Exception as e:
        _log_error(f"TTS worker exception: {e}")
        _worker_powershell_fallback()
    finally:
        if voice_ptr.value is not None:
            try:
                release_fn = _get_vtbl_func(voice_ptr.value, VTBL_RELEASE, ctypes.c_ulong)
                release_fn(voice_ptr.value)
            except Exception:
                pass
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def _worker_powershell_fallback():
    """Fallback TTS using PowerShell Add-Type with SAPI."""
    import subprocess
    global _running
    _log("Using PowerShell TTS fallback")

    while _running:
        try:
            text, interrupt = _speech_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if not text:
            continue

        try:
            # Use PowerShell to speak (blocking per utterance but in background thread)
            escaped = text.replace("'", "''").replace('"', '`"')
            cmd = f'powershell -Command "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate = {_rate}; $s.Volume = {_volume}; $s.Speak(\'{escaped}\')"'
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            _log_error(f"PowerShell TTS failed: {e}")


def init():
    """Initialize the TTS system."""
    global _worker_thread, _running
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _running = True
    _worker_thread = threading.Thread(target=_worker, daemon=True, name="BL2A11y-TTS")
    _worker_thread.start()
    _log("TTS system initialized")


def shutdown():
    """Shut down the TTS system."""
    global _running
    _running = False
    if _worker_thread is not None:
        _worker_thread.join(timeout=2.0)
    _log("TTS system shut down")


def speak(text: str, interrupt: bool = True):
    """Speak text via TTS."""
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
    """Stop current speech."""
    while not _speech_queue.empty():
        try:
            _speech_queue.get_nowait()
        except queue.Empty:
            break
    _speech_queue.put(("", True))


def set_rate(rate: int):
    """Set speech rate (-10 to 10)."""
    global _rate
    _rate = max(-10, min(10, rate))


def set_volume(vol: int):
    """Set speech volume (0-100)."""
    global _volume
    _volume = max(0, min(100, vol))
