"""
Startup Helper - Gets blind players through BL2 startup.

Known BL2 startup sequence (from logs):
1. SDK loads ~20s after game launch (during splash/logo movies)
2. Splash movies play (Gearbox/2K logos) — these ARE the "cutscene"
3. WillowGFxMoviePressStart already exists (:Start fired before SDK loaded)
4. User presses any key → press start screen dismisses
5. OnlineMessageGFxMovie:Start — Shift account popup
6. UpsellNotificationGFxMovie:Start — DLC promo
7. FrontendGFxMovie:Start — Main menu

Key constraints:
- PressStart:Start fires BEFORE SDK loads, so we can't hook it
- Scaleform menus don't route keyboard through Unreal (no input hooks work)
- Must use delayed detection for press-start screen
- Auto-continue uses LaunchSaveGame(0) which works
"""

import unrealsdk
from unrealsdk import hooks, logging as sdk_logging
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction
import threading
import time

from . import tts

_announced = set()
_at_main_menu = False
_game_loaded = False


def _announce_once(key: str, text: str, interrupt: bool = True):
    """Speak text only once per key."""
    if key not in _announced:
        _announced.add(key)
        tts.speak(text, interrupt)
        sdk_logging.info(f"[BL2A11y] Announced: {key}")


# =============================================================================
# DELAYED PRESS-START DETECTION
# Since PressStart:Start fires before SDK loads, we use a delayed thread
# that waits for splash movies to finish then announces.
# =============================================================================

def _delayed_press_start_check():
    """Wait for splash movies to end, then announce press-start screen."""
    # Splash movies take ~15-20 seconds. SDK loads during them.
    # Wait until they're likely done before announcing.
    time.sleep(12.0)
    sdk_logging.info("[BL2A11y] Checking for press-start screen")

    # Check if we're still at the press-start screen (no frontend yet)
    if "main_menu" not in _announced and not _at_main_menu:
        _announce_once("press_start", "Press any key to start.", True)


# =============================================================================
# ONLINE MESSAGE (Shift popup) — auto-dismiss + capture what was clicked
# =============================================================================

def _on_online_message_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """OnlineMessageGFxMovie shown — Shift account popup. Auto-dismiss."""
    sdk_logging.info("[BL2A11y] OnlineMessage shown - dismissing")
    tts.speak("Online popup. Dismissing.", True)
    try:
        obj.Close()
        sdk_logging.info("[BL2A11y] OnlineMessage dismissed via Close")
    except Exception as e:
        sdk_logging.error(f"[BL2A11y] OnlineMessage Close failed: {e}")


# =============================================================================
# EULA — auto-accept
# =============================================================================

def _on_eula_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """EULA shown — auto-accept."""
    sdk_logging.info("[BL2A11y] EULA shown - accepting")
    tts.speak("License agreement. Accepting.", True)
    for method in ['Accept', 'OnAccept', 'Close']:
        try:
            getattr(obj, method)()
            sdk_logging.info(f"[BL2A11y] EULA accepted via {method}")
            return
        except Exception:
            continue


# =============================================================================
# UPSELL — auto-dismiss
# =============================================================================

def _on_upsell_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """UpsellNotification shown — auto-dismiss."""
    sdk_logging.info("[BL2A11y] Upsell shown - dismissing")
    tts.speak("Promotional popup. Dismissing.", True)
    try:
        obj.Close()
    except Exception:
        pass


# =============================================================================
# MAIN MENU — announce and auto-continue
# =============================================================================

def _on_frontend_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """FrontendGFxMovie shown — main menu. Auto-continue after delay."""
    global _at_main_menu
    _at_main_menu = True
    sdk_logging.info("[BL2A11y] Frontend/main menu shown")
    tts.speak("Main menu. Loading your saved game in 5 seconds.", True)

    def _auto_continue():
        time.sleep(5.0)
        if not _at_main_menu or _game_loaded:
            return
        sdk_logging.info("[BL2A11y] Auto-continuing saved game...")
        tts.speak("Loading saved game.", True)
        try:
            for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
                if movie is None:
                    continue
                # LaunchSaveGame(PlayThrough) — 0=Normal
                try:
                    movie.LaunchSaveGame(0)
                    sdk_logging.info("[BL2A11y] Continue via LaunchSaveGame(0)")
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] LaunchSaveGame(0): {e}")
                # Try OpenCharacterSelect as fallback (for new players)
                try:
                    movie.OpenCharacterSelect()
                    sdk_logging.info("[BL2A11y] Opened character select")
                    tts.speak("Character selection. Choose your character.", True)
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] OpenCharacterSelect: {e}")
        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Auto-continue failed: {e}")
    threading.Thread(target=_auto_continue, daemon=True).start()


# =============================================================================
# DIALOG BOXES — read text + auto-accept
# =============================================================================

def _on_dialog_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Any dialog box shown."""
    sdk_logging.info(f"[BL2A11y] Dialog shown")
    text = ""
    for attr in ['DialogText', 'MessageText', 'Body', 'Text', 'Description',
                  'sDialog', 'sMessage', 'sBody', 'DialogBody', 'sText']:
        try:
            val = getattr(obj, attr, None)
            if val is not None:
                t = str(val).strip()
                if t and len(t) > 2:
                    text = t
                    break
        except Exception:
            continue
    if text:
        tts.speak(f"Dialog. {text}. Accepting.", True)
    else:
        tts.speak("Dialog popup. Accepting.", True)
    for method in ['Accept', 'OnAccept', 'AcceptClicked', 'OKClicked', 'Close']:
        try:
            getattr(obj, method)()
            sdk_logging.info(f"[BL2A11y] Dialog accepted via {method}")
            return
        except Exception:
            continue


# =============================================================================
# LOADING SCREENS
# =============================================================================

def _on_loading_movie(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Loading movie shown."""
    tts.speak("Loading.", True)
    sdk_logging.info("[BL2A11y] Loading screen shown")


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """World loaded — now in gameplay."""
    global _at_main_menu, _game_loaded
    _at_main_menu = False
    _game_loaded = True
    _announced.discard("main_menu")
    _announced.discard("press_start")
    sdk_logging.info("[BL2A11y] World loaded")
    tts.speak("Loading complete. W A S D to move. I J K L to look around. Spacebar to fire. F to interact. F1 for health. F4 for full status.", True)


def _on_map_change(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Map transition."""
    tts.speak("Loading.", True)
    sdk_logging.info("[BL2A11y] Map change")


# =============================================================================
# PAUSE MENU
# =============================================================================

def _on_pause_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Pause menu shown."""
    tts.speak("Pause menu.", True)


# =============================================================================
# INTRO/SPLASH MOVIES
# =============================================================================

def _on_fullscreen_movie(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Fullscreen movie started (splash logos)."""
    sdk_logging.info("[BL2A11y] Fullscreen movie playing")
    _announce_once("splash", "Loading Borderlands 2.", True)


# =============================================================================
# CONSOLE COMMANDS (backup)
# =============================================================================

def _cmd_continue(line: str, cmd_len: int):
    """Console: type 'continue' to load saved game."""
    tts.speak("Loading saved game.", True)
    try:
        for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
            if movie is None:
                continue
            try:
                movie.LaunchSaveGame(0)
                return
            except Exception:
                pass
    except Exception:
        pass


def _cmd_newgame(line: str, cmd_len: int):
    """Console: type 'newgame' to start new game."""
    tts.speak("Starting new game.", True)
    try:
        for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
            if movie is None:
                continue
            try:
                movie.LaunchNewGame()
                return
            except Exception:
                pass
    except Exception:
        pass


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

_HOOKS = [
    ("WillowGame.OnlineMessageGFxMovie:Start", hooks.Type.POST, "bl2a11y_online_msg", _on_online_message_show),
    ("WillowGame.GearboxEULAGFxMovie:Start", hooks.Type.POST, "bl2a11y_eula", _on_eula_show),
    ("WillowGame.UpsellNotificationGFxMovie:Start", hooks.Type.POST, "bl2a11y_upsell", _on_upsell_show),
    ("WillowGame.FrontendGFxMovie:Start", hooks.Type.POST, "bl2a11y_frontend", _on_frontend_show),
    ("WillowGame.WillowGFxDialogBox:Start", hooks.Type.POST, "bl2a11y_dialog", _on_dialog_show),
    ("WillowGame.WillowGFxTrainingDialogBox:Start", hooks.Type.POST, "bl2a11y_training_dialog", _on_dialog_show),
    ("WillowGame.WillowPlayerController:WillowClientShowLoadingMovie", hooks.Type.POST, "bl2a11y_loading", _on_loading_movie),
    ("Engine.PlayerController:NotifyLoadedWorld", hooks.Type.POST, "bl2a11y_loaded", _on_loading_complete),
    ("Engine.WorldInfo:PreCommitMapChange", hooks.Type.PRE, "bl2a11y_mapchange", _on_map_change),
    ("WillowGame.PauseGFxMovie:Start", hooks.Type.POST, "bl2a11y_pause", _on_pause_show),
    ("Engine.GameViewportClient:ShowFullScreenMovie", hooks.Type.POST, "bl2a11y_fullscreen", _on_fullscreen_movie),
]


def register_hooks():
    """Register all startup helper hooks."""
    from unrealsdk import commands
    for func_name, hook_type, identifier, callback in _HOOKS:
        try:
            hooks.add_hook(func_name, hook_type, identifier, callback)
        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Failed to hook {func_name}: {e}")

    try:
        commands.add_command("continue", _cmd_continue)
        commands.add_command("newgame", _cmd_newgame)
    except Exception:
        pass

    # Start delayed press-start detection (waits for splash movies to end)
    threading.Thread(target=_delayed_press_start_check, daemon=True).start()
    sdk_logging.info("[BL2A11y Startup] All hooks registered")


def unregister_hooks():
    """Remove all startup helper hooks."""
    for func_name, hook_type, identifier, callback in _HOOKS:
        try:
            hooks.remove_hook(func_name, hook_type, identifier)
        except Exception:
            pass
    try:
        from unrealsdk import commands
        commands.remove_command("continue")
        commands.remove_command("newgame")
    except Exception:
        pass
