"""
Startup Helper - Gets blind players through BL2 startup.

APPROACH: Hook specific functions that fire when screens actually become active.
find_all() returns ALL pre-created movie instances, so polling doesn't work.
Instead we hook into the actual Show/Start/Open methods on specific movies.
"""

import unrealsdk
from unrealsdk import hooks, logging as sdk_logging
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts

_announced = set()
_at_main_menu = False


def _announce_once(key: str, text: str, interrupt: bool = True):
    """Speak text only once per key."""
    if key not in _announced:
        _announced.add(key)
        tts.speak(text, interrupt)
        sdk_logging.info(f"[BL2A11y] Announced: {key}")


# =============================================================================
# SPLASH / INTRO MOVIES
# =============================================================================

def _on_start_intro_movies(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Startup movies (logos) beginning to play."""
    sdk_logging.info("[BL2A11y] Intro movies starting")
    tts.speak("Loading Borderlands 2.", True)


# =============================================================================
# PRESS START SCREEN
# =============================================================================

def _on_press_start_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """WillowGFxMoviePressStart is now visible."""
    sdk_logging.info("[BL2A11y] PressStart shown")
    _announce_once("press_start", "Press any key to start.", True)


# =============================================================================
# EULA
# =============================================================================

def _on_eula_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """EULA screen shown — auto-accept it."""
    sdk_logging.info("[BL2A11y] EULA shown")
    tts.speak("License agreement. Accepting.", True)
    try:
        obj.Accept()
    except Exception:
        try:
            obj.OnAccept()
        except Exception:
            try:
                obj.Close()
            except Exception:
                pass


# =============================================================================
# ONLINE MESSAGE (Shift account popup)
# =============================================================================

def _on_online_message_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """OnlineMessageGFxMovie shown — the Shift account popup. Auto-dismiss."""
    sdk_logging.info("[BL2A11y] OnlineMessage shown - dismissing")
    tts.speak("Online account popup. Dismissing.", True)
    # Try every possible way to close it
    for method in ['Close', 'Accept', 'OnAccept', 'AcceptClicked', 'OKClicked',
                   'Dismiss', 'OnClose', 'Cancel', 'OnCancel', 'Skip', 'OnSkip',
                   'Acknowledged', 'OnAcknowledged', 'ExternalClose']:
        try:
            getattr(obj, method)()
            sdk_logging.info(f"[BL2A11y] OnlineMessage dismissed via {method}")
            return
        except Exception:
            continue


# =============================================================================
# UPSELL / DLC PROMO
# =============================================================================

def _on_upsell_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """UpsellNotificationGFxMovie shown — auto-dismiss."""
    sdk_logging.info("[BL2A11y] Upsell shown - dismissing")
    tts.speak("Promotional popup. Dismissing.", True)
    try:
        obj.Close()
    except Exception:
        pass


# =============================================================================
# MAIN MENU (Frontend)
# =============================================================================

def _on_frontend_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """FrontendGFxMovie shown — the main menu. Auto-continue after delay."""
    global _at_main_menu
    _at_main_menu = True
    sdk_logging.info("[BL2A11y] Frontend/main menu shown")
    tts.speak("Main menu. Loading your saved game in 5 seconds.", True)

    # Auto-continue after 5 seconds. Key input hooks don't work at the menu
    # because Scaleform/Flash handles input directly without going through Unreal.
    import threading
    def _auto_continue():
        import time
        time.sleep(5.0)
        if not _at_main_menu:
            return  # Already left the menu
        sdk_logging.info("[BL2A11y] Auto-continuing saved game...")
        tts.speak("Loading saved game.", True)
        try:
            for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
                if movie is None:
                    continue
                try:
                    movie.ConditionalLoadGame()
                    sdk_logging.info("[BL2A11y] Continue via ConditionalLoadGame")
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] ConditionalLoadGame: {e}")
                try:
                    movie.LaunchSaveGame()
                    sdk_logging.info("[BL2A11y] Continue via LaunchSaveGame")
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] LaunchSaveGame: {e}")
                try:
                    movie.LaunchNewGame()
                    sdk_logging.info("[BL2A11y] Fallback: LaunchNewGame")
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] LaunchNewGame: {e}")
        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Auto-continue failed: {e}")
        tts.speak("Could not auto-continue. Use tilde key to open console, then type continue.", True)
    threading.Thread(target=_auto_continue, daemon=True).start()


# =============================================================================
# DIALOG BOXES
# =============================================================================

def _on_dialog_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Any WillowGFxDialogBox shown."""
    sdk_logging.info(f"[BL2A11y] Dialog box shown: {obj}")
    # Try to read dialog text
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

    # Auto-accept
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

def _on_loading_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Loading movie shown."""
    sdk_logging.info("[BL2A11y] Loading screen")
    tts.speak("Loading.", True)


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """World loaded."""
    sdk_logging.info("[BL2A11y] World loaded")
    _announced.discard("main_menu")
    tts.speak("Loading complete.", True)


def _on_map_change(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Map transition."""
    sdk_logging.info("[BL2A11y] Map change")
    tts.speak("Loading.", True)


# =============================================================================
# PAUSE MENU
# =============================================================================

def _on_pause_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Pause menu shown."""
    tts.speak("Pause menu.", True)


# =============================================================================
# RAW INPUT HOOK - works at ALL screens including menus
# =============================================================================

def _on_viewport_input_key(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """
    Fires on EVERY key press at every screen (menus, gameplay, everything).
    Used to handle F7/F8 at main menu where mod keybinds don't work.
    """
    global _at_main_menu
    try:
        key = ""
        event = -1
        # Try different arg names
        for attr in ['Key', 'ukey', 'KeyName']:
            try:
                val = getattr(args, attr, None)
                if val is not None:
                    key = str(val)
                    break
            except Exception:
                continue
        for attr in ['EventType', 'Event', 'InputEvent', 'eEvent']:
            try:
                val = getattr(args, attr, None)
                if val is not None:
                    event = int(val)
                    break
            except Exception:
                continue

        # IE_Pressed = 0
        if event != 0:
            return

        sdk_logging.info(f"[BL2A11y Input] Key: {key}")

        if key == "F7":
            tts.speak("Continuing game.", True)
            sdk_logging.info("[BL2A11y Input] F7 pressed - trying to continue")
            try:
                for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
                    if movie is None:
                        continue
                    # From the actual method list: ConditionalLoadGame, LaunchSaveGame
                    for method in ['ConditionalLoadGame', 'LaunchSaveGame', 'LaunchSaveGameEx']:
                        try:
                            getattr(movie, method)()
                            sdk_logging.info(f"[BL2A11y] Continue via {method}")
                            return hooks.Block
                        except Exception as e:
                            sdk_logging.info(f"[BL2A11y] {method} failed: {e}")
                            continue
            except Exception as e:
                sdk_logging.error(f"[BL2A11y] Continue failed: {e}")
            return hooks.Block

        elif key == "F8":
            tts.speak("Starting new game.", True)
            sdk_logging.info("[BL2A11y Input] F8 pressed - trying new game")
            try:
                for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
                    if movie is None:
                        continue
                    # From the actual method list: LaunchNewGame
                    try:
                        movie.LaunchNewGame()
                        sdk_logging.info("[BL2A11y] New game via LaunchNewGame")
                        return hooks.Block
                    except Exception as e:
                        sdk_logging.info(f"[BL2A11y] LaunchNewGame failed: {e}")
            except Exception as e:
                sdk_logging.error(f"[BL2A11y] New game failed: {e}")
            return hooks.Block

    except Exception as e:
        sdk_logging.error(f"[BL2A11y Input] Error: {e}")


# =============================================================================
# HOOK REGISTRATION
# All hooks use the :Start method which fires when a movie ACTUALLY opens.
# =============================================================================

# =============================================================================
# CONSOLE COMMANDS (backup — type in ~ console)
# =============================================================================

def _cmd_continue(line: str, cmd_len: int):
    """Console command: type 'continue' to load saved game."""
    sdk_logging.info("[BL2A11y] Console: continue command")
    tts.speak("Loading saved game.", True)
    try:
        for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
            if movie is None:
                continue
            try:
                movie.ConditionalLoadGame()
                return
            except Exception:
                pass
            try:
                movie.LaunchSaveGame()
                return
            except Exception:
                pass
    except Exception:
        pass


def _cmd_newgame(line: str, cmd_len: int):
    """Console command: type 'newgame' to start new game."""
    sdk_logging.info("[BL2A11y] Console: newgame command")
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


_HOOKS = [
    # (unreal_function, hook_type, identifier, callback)

    # Press start screen
    ("WillowGame.WillowGFxMoviePressStart:Start", hooks.Type.POST, "bl2a11y_pressstart", _on_press_start_show),

    # EULA
    ("WillowGame.GearboxEULAGFxMovie:Start", hooks.Type.POST, "bl2a11y_eula", _on_eula_show),

    # Online message (Shift popup)
    ("WillowGame.OnlineMessageGFxMovie:Start", hooks.Type.POST, "bl2a11y_online_msg", _on_online_message_show),

    # Upsell
    ("WillowGame.UpsellNotificationGFxMovie:Start", hooks.Type.POST, "bl2a11y_upsell", _on_upsell_show),

    # Main menu
    ("WillowGame.FrontendGFxMovie:Start", hooks.Type.POST, "bl2a11y_frontend", _on_frontend_show),

    # Dialog boxes
    ("WillowGame.WillowGFxDialogBox:Start", hooks.Type.POST, "bl2a11y_dialog", _on_dialog_show),
    ("WillowGame.WillowGFxTrainingDialogBox:Start", hooks.Type.POST, "bl2a11y_training_dialog", _on_dialog_show),

    # Loading
    ("WillowGame.WillowPlayerController:WillowClientShowLoadingMovie", hooks.Type.POST, "bl2a11y_loading", _on_loading_start),
    ("Engine.PlayerController:NotifyLoadedWorld", hooks.Type.POST, "bl2a11y_loaded", _on_loading_complete),
    ("Engine.WorldInfo:PreCommitMapChange", hooks.Type.PRE, "bl2a11y_mapchange", _on_map_change),

    # Pause
    ("WillowGame.PauseGFxMovie:Start", hooks.Type.POST, "bl2a11y_pause", _on_pause_show),

    # Intro movies
    ("Engine.GameViewportClient:ShowFullScreenMovie", hooks.Type.POST, "bl2a11y_fullscreen_movie", _on_start_intro_movies),

    # Note: keyboard input hooks don't work at BL2 menus (Scaleform handles input directly).
    # F7/F8 keybinds only work during gameplay. At main menu, we auto-continue after 5 seconds.
]


def register_hooks():
    """Register all startup helper hooks."""
    from unrealsdk import commands
    for func_name, hook_type, identifier, callback in _HOOKS:
        try:
            hooks.add_hook(func_name, hook_type, identifier, callback)
            sdk_logging.info(f"[BL2A11y] Hook registered: {func_name}")
        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Failed to hook {func_name}: {e}")
    # Register console commands
    try:
        commands.add_command("continue", _cmd_continue)
        commands.add_command("newgame", _cmd_newgame)
        sdk_logging.info("[BL2A11y] Console commands registered: continue, newgame")
    except Exception as e:
        sdk_logging.error(f"[BL2A11y] Console command registration failed: {e}")
    sdk_logging.info("[BL2A11y Startup] All hooks registered")


def unregister_hooks():
    """Remove all startup helper hooks."""
    for func_name, hook_type, identifier, callback in _HOOKS:
        try:
            hooks.remove_hook(func_name, hook_type, identifier)
        except Exception:
            pass
