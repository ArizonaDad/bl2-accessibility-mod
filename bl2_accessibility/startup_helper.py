"""
Startup Helper - Handles BL2 startup popups and screens for blind players.

Uses multiple hook strategies since BL2 uses different class hierarchies:
- WillowGame.FrontendGFxMovie for main menu
- WillowGame.WillowGFxDialogBox for popups/EULA
- Engine.GameViewportClient for "press any key"
- Timed polling as fallback to catch anything hooks miss
"""

import unrealsdk
from unrealsdk import hooks, logging as sdk_logging
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction
import threading
import time

from . import tts

_announced = set()
_polling_active = False
_poll_thread = None


def _announce_once(key: str, text: str, interrupt: bool = True):
    """Speak text only once per key (prevents repeats)."""
    if key not in _announced:
        _announced.add(key)
        tts.speak(text, interrupt)
        sdk_logging.info(f"[BL2A11y Startup] Announced: {key}")


# =============================================================================
# POLLING THREAD - Scans for active movies/dialogs every second
# =============================================================================

def _poll_for_screens():
    """Background thread that polls for active GFx movies and announces them."""
    global _polling_active
    sdk_logging.info("[BL2A11y Startup] Polling thread started")

    while _polling_active:
        time.sleep(1.5)
        try:
            # Scan ALL GFxMoviePlayer instances
            try:
                for movie in unrealsdk.find_all("GFxMoviePlayer", exact=False):
                    if movie is None:
                        continue
                    try:
                        cls = str(movie.Class.Name)
                        name = str(movie.Name)
                        visible = True
                        try:
                            visible = bool(movie.bMovieIsOpen) if hasattr(movie, 'bMovieIsOpen') else True
                        except Exception:
                            pass
                        if not visible:
                            continue

                        lower_cls = cls.lower()
                        lower_name = name.lower()
                        sdk_logging.info(f"[BL2A11y Poll] Active movie: cls={cls} name={name}")

                        _identify_and_announce(cls, name, lower_cls, lower_name, movie)
                    except Exception:
                        continue
            except Exception as e:
                sdk_logging.error(f"[BL2A11y Poll] find_all error: {e}")

            # Also check for dialog boxes specifically
            try:
                for dialog in unrealsdk.find_all("WillowGFxDialogBox", exact=False):
                    if dialog is None:
                        continue
                    try:
                        cls = str(dialog.Class.Name)
                        sdk_logging.info(f"[BL2A11y Poll] Dialog found: {cls}")
                        _announce_once("dialog_" + cls, "Dialog box. Press enter to accept or escape to cancel.", True)
                    except Exception:
                        continue
            except Exception:
                pass

        except Exception as e:
            sdk_logging.error(f"[BL2A11y Poll] Error: {e}")

    sdk_logging.info("[BL2A11y Startup] Polling thread stopped")


def _identify_and_announce(cls, name, lower_cls, lower_name, movie):
    """Identify a GFx movie and announce it."""
    key = cls + "_" + name

    # Main menu / Frontend
    if "frontend" in lower_cls:
        _announce_once("main_menu", "Main menu. Continue, New game, Downloadable content, Mods, Options, Quit. Use up and down arrows. Press enter to select.", True)
        return

    # EULA / License
    if "eula" in lower_cls or "eula" in lower_name or "license" in lower_cls:
        _announce_once("eula", "License agreement. Press enter to accept.", True)
        return

    # Dialog box
    if "dialog" in lower_cls:
        # Try to read dialog text
        text = ""
        for attr in ['DialogText', 'MessageText', 'Body', 'Text', 'Description']:
            try:
                val = getattr(movie, attr, None)
                if val is not None:
                    text = str(val).strip()
                    if text:
                        break
            except Exception:
                continue
        if text:
            _announce_once(key, f"Dialog. {text}. Press enter to accept or escape to cancel.", True)
        else:
            _announce_once(key, "Dialog box. Press enter to accept or escape to cancel.", True)
        return

    # Pause menu
    if "pause" in lower_cls:
        _announce_once("pause", "Pause menu.", True)
        return

    # Character select
    if "character" in lower_cls or "charsel" in lower_cls:
        _announce_once("charsel", "Character selection. Left and right to choose. Enter to select.", True)
        return

    # Vending
    if "vending" in lower_cls or "vendor" in lower_cls:
        _announce_once("vendor", "Vending machine.", True)
        return

    # Status menu
    if "status" in lower_cls:
        _announce_once("status", "Status menu.", True)
        return

    # Attract mode / press any key
    if "attract" in lower_cls or "pressstart" in lower_cls or "pressanykey" in lower_name:
        _announce_once("press_start", "Title screen. Press enter to start.", True)
        return

    # Loading
    if "loading" in lower_cls or "loading" in lower_name:
        _announce_once("loading_" + name, "Loading.", True)
        return

    # Sparks / SHIFT
    if "sparks" in lower_cls or "shift" in lower_cls:
        _announce_once("shift", "Shift popup. Press escape to skip.", True)
        return

    # Ads / promo / MOTD
    if "motd" in lower_cls or "ad" in lower_cls or "promo" in lower_cls or "upsell" in lower_cls:
        _announce_once("promo", "Promotional popup. Press escape to dismiss.", True)
        return

    # HUD - don't announce
    if "hud" in lower_cls or "hud" in lower_name:
        return

    # Unknown - announce once
    friendly = cls.replace("GFxMovie", "").replace("Movie", "").replace("GFx", "")
    if friendly:
        _announce_once(key, f"{friendly} screen.", False)


# =============================================================================
# HOOK-BASED DETECTION (fires when specific functions are called)
# =============================================================================

def _on_frontend_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Main menu opened."""
    _announce_once("main_menu", "Main menu. Continue, New game, Downloadable content, Mods, Options, Quit. Use up and down arrows. Press enter to select.", True)


def _on_dialog_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Any dialog box shown."""
    sdk_logging.info(f"[BL2A11y] Dialog show hook fired: {obj}")
    text = ""
    for attr in ['DialogText', 'MessageText', 'Body', 'Text', 'Description']:
        try:
            val = getattr(obj, attr, None)
            if val is not None:
                text = str(val).strip()
                if text:
                    break
        except Exception:
            continue
    if text:
        tts.speak(f"Dialog. {text}. Press enter to accept or escape to cancel.", True)
    else:
        tts.speak("Dialog box. Press enter to accept or escape to cancel.", True)


def _on_loading_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Loading screen started."""
    tts.speak("Loading.", True)


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Loading finished."""
    # Reset announced set so screens can re-announce
    _announced.discard("main_menu")
    _announced.discard("loading")
    tts.speak("Loading complete.", True)


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all startup helper hooks."""
    global _polling_active, _poll_thread

    # Hook-based detection
    hooks.add_hook(
        "WillowGame.FrontendGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_frontend_start2", _on_frontend_start
    )

    hooks.add_hook(
        "Engine.PlayerController:NotifyLoadedWorld",
        hooks.Type.POST, "bl2a11y_loaded2", _on_loading_complete
    )

    # Start polling thread as fallback
    _polling_active = True
    _poll_thread = threading.Thread(target=_poll_for_screens, daemon=True, name="BL2A11y-Poll")
    _poll_thread.start()
    sdk_logging.info("[BL2A11y Startup] Hooks registered + polling started")


def unregister_hooks():
    """Remove all startup helper hooks."""
    global _polling_active
    _polling_active = False

    hooks.remove_hook("WillowGame.FrontendGFxMovie:Start", hooks.Type.POST, "bl2a11y_frontend_start2")
    hooks.remove_hook("Engine.PlayerController:NotifyLoadedWorld", hooks.Type.POST, "bl2a11y_loaded2")
