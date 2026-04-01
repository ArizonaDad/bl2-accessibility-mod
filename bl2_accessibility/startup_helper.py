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
_press_start_active = False  # Track if PressStart screen is still showing
_last_loading_announced = 0  # Timestamp of last loading announcement


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
            global _press_start_active
            # Collect all active movies this cycle
            active_classes = set()
            movies_list = []
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
                        active_classes.add(cls.lower())
                        movies_list.append((cls, name, movie))
                    except Exception:
                        continue
            except Exception as e:
                sdk_logging.error(f"[BL2A11y Poll] find_all error: {e}")

            # Track press-start state
            _press_start_active = "willowgfxmoviepressstart" in active_classes

            # Check if we're in a loading state (no movies at all, or only minimal ones)
            if len(movies_list) == 0:
                _announce_once("loading_empty", "Loading.", True)

            # Process each movie
            for cls, name, movie in movies_list:
                lower_cls = cls.lower()
                lower_name = name.lower()
                # Only log non-spammy ones
                if "weaponscope" not in lower_cls:
                    sdk_logging.info(f"[BL2A11y Poll] Active movie: cls={cls} name={name}")
                _identify_and_announce(cls, name, lower_cls, lower_name, movie)

            # Re-attempt dismissing known blocking popups every poll cycle
            try:
                for movie in unrealsdk.find_all("GFxMoviePlayer", exact=False):
                    if movie is None:
                        continue
                    try:
                        cls = str(movie.Class.Name).lower()
                        visible = True
                        try:
                            visible = bool(movie.bMovieIsOpen) if hasattr(movie, 'bMovieIsOpen') else True
                        except Exception:
                            pass
                        if not visible:
                            continue
                        # Keep trying to close blocking popups
                        if any(x in cls for x in ["onlinemessage", "upsell", "dialog", "sparks"]):
                            _try_close_movie(movie)
                    except Exception:
                        continue
            except Exception:
                pass

        except Exception as e:
            sdk_logging.error(f"[BL2A11y Poll] Error: {e}")

    sdk_logging.info("[BL2A11y Startup] Polling thread stopped")


def _read_frontend_menu(movie) -> str:
    """Try to read actual menu item labels from the frontend GFx movie."""
    items = []
    try:
        # Try common Scaleform menu properties
        for attr in ['MenuItems', 'Items', 'ButtonList', 'Buttons', 'MenuOptions']:
            try:
                arr = getattr(movie, attr, None)
                if arr is not None:
                    for item in arr:
                        if item is not None:
                            for text_attr in ['Label', 'Text', 'Caption', 'Name', 'ButtonText']:
                                try:
                                    t = str(getattr(item, text_attr, "")).strip()
                                    if t and len(t) > 1:
                                        items.append(t)
                                        break
                                except Exception:
                                    continue
            except Exception:
                continue
    except Exception:
        pass

    if items:
        return ", ".join(items)

    # Fallback: known BL2 main menu order
    return "Continue, New Game, Downloadable Content, Mods, Options, Quit"


def _try_close_movie(movie):
    """Attempt to programmatically close/dismiss a GFx movie."""
    # Try every known close method
    for method_name in [
        'Close', 'OnClose', 'CloseMovie', 'Dismiss', 'OnDismiss',
        'Accept', 'OnAccept', 'AcceptClicked', 'OKClicked', 'OnOK',
        'ExternalClose', 'ExtClose', 'ForceClose', 'CloseDialog',
        'OnCancel', 'Cancel', 'Cancelled',
    ]:
        try:
            fn = getattr(movie, method_name, None)
            if fn is not None:
                fn()
                sdk_logging.info(f"[BL2A11y] Dismissed via {method_name}")
                return True
        except Exception:
            continue
    # Try setting visibility
    try:
        movie.bMovieIsOpen = False
    except Exception:
        pass
    # Last resort: call Close with no args via the Unreal function system
    try:
        movie.Close(True)
    except Exception:
        pass
    return False


def _identify_and_announce(cls, name, lower_cls, lower_name, movie):
    """Identify a GFx movie and announce/dismiss it."""
    key = cls + "_" + name

    # Main menu / Frontend — only announce when PressStart is gone
    if "frontend" in lower_cls:
        if not _press_start_active:
            # Try to read actual menu items from the movie
            menu_text = _read_frontend_menu(movie)
            if menu_text:
                _announce_once("main_menu", f"Main menu. {menu_text}. Use up and down arrows. Press enter to select.", True)
            else:
                _announce_once("main_menu", "Main menu. Use up and down arrows. Press enter to select.", True)
            # Ensure the menu can receive keyboard input
            try:
                movie.SetFocus(True)
            except Exception:
                pass
            try:
                movie.GrabFocus()
            except Exception:
                pass
        return

    # Press Start screen
    if "pressstart" in lower_cls:
        _announce_once("press_start", "Press any key to start.", True)
        return

    # Online Message (Shift account popup) — AUTO-DISMISS and keep retrying
    if "onlinemessage" in lower_cls:
        _announce_once("online_msg", "Online message. Dismissing.", True)
        _try_close_movie(movie)
        # Also try clicking accept/ok buttons
        try:
            movie.AcceptClicked()
        except Exception:
            pass
        try:
            movie.OnAcceptClicked()
        except Exception:
            pass
        return

    # Upsell / DLC promo — AUTO-DISMISS
    if "upsell" in lower_cls:
        _announce_once("upsell", "Promotional popup. Dismissing automatically.", True)
        _try_close_movie(movie)
        return

    # EULA / License
    if "eula" in lower_cls or "eula" in lower_name or "license" in lower_cls:
        _announce_once("eula", "License agreement. Accepting automatically.", True)
        _try_close_movie(movie)
        return

    # Dialog boxes — read text then auto-accept
    if "dialog" in lower_cls:
        text = ""
        for attr in ['DialogText', 'MessageText', 'Body', 'Text', 'Description',
                      'sDialog', 'sMessage', 'sBody', 'DialogBody']:
            try:
                val = getattr(movie, attr, None)
                if val is not None:
                    t = str(val).strip()
                    if t and len(t) > 2:
                        text = t
                        break
            except Exception:
                continue
        if text:
            _announce_once(key, f"Dialog. {text}. Accepting.", True)
        else:
            _announce_once(key, "Dialog popup. Accepting.", True)
        # Auto-accept dialog boxes to get through startup
        _try_close_movie(movie)
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

    # Loading
    if "loading" in lower_cls or "loading" in lower_name:
        _announce_once("loading_" + name, "Loading.", True)
        return

    # Sparks / SHIFT
    if "sparks" in lower_cls or "shift" in lower_cls:
        _announce_once("shift", "Shift popup. Dismissing.", True)
        _try_close_movie(movie)
        return

    # Ads / promo / MOTD
    if "motd" in lower_cls or "promo" in lower_cls:
        _announce_once("promo", "Promotional popup. Dismissing.", True)
        _try_close_movie(movie)
        return

    # WeaponScope — ignore silently
    if "weaponscope" in lower_cls:
        return

    # HUD — ignore silently
    if "hud" in lower_cls or "hud" in lower_name:
        return

    # Unknown movie — announce but don't dismiss
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
    """Loading screen started — called on map transitions."""
    tts.speak("Loading.", True)


def _on_loading_movie(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a loading movie/screen is shown."""
    tts.speak("Loading.", True)


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Loading finished."""
    # Reset announced set so screens can re-announce on next visit
    _announced.discard("main_menu")
    _announced.discard("loading_empty")
    tts.speak("Loading complete.", True)


def _on_map_change(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called on map change / travel."""
    tts.speak("Loading.", True)


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

    # Loading detection - multiple hooks for different loading scenarios
    hooks.add_hook(
        "Engine.PlayerController:NotifyLoadedWorld",
        hooks.Type.POST, "bl2a11y_loaded2", _on_loading_complete
    )

    hooks.add_hook(
        "WillowGame.WillowPlayerController:WillowClientShowLoadingMovie",
        hooks.Type.POST, "bl2a11y_loading_movie", _on_loading_movie
    )

    hooks.add_hook(
        "Engine.WorldInfo:PreCommitMapChange",
        hooks.Type.PRE, "bl2a11y_map_change", _on_map_change
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
    hooks.remove_hook("WillowGame.WillowPlayerController:WillowClientShowLoadingMovie", hooks.Type.POST, "bl2a11y_loading_movie")
    hooks.remove_hook("Engine.WorldInfo:PreCommitMapChange", hooks.Type.PRE, "bl2a11y_map_change")
