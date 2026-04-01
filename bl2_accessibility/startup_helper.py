"""
Startup Helper - Gets blind players through BL2 startup.

FIRST LAUNCH: SHiFT account registration appears (OnlineMessageGFxMovie).
This is a Scaleform Flash dialog that can't be dismissed programmatically.
Close() returns success but the popup stays visually.
A sighted person must click through it ONCE (username, confirm).
After first launch, it never appears again.

SUBSEQUENT LAUNCHES: OnlineMessage auto-dismissed, straight to main menu.

Known startup sequence:
1. Splash movies (~15s)
2. Press any key screen (PressStart already exists before SDK)
3. OnlineMessage — first launch: SHiFT registration. Later: auto-dismissed.
4. UpsellNotification — auto-dismissed
5. FrontendGFxMovie — Main menu (arrow keys work!)
"""

import unrealsdk
from unrealsdk import hooks, logging as sdk_logging
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction
import threading
import time
import os

from . import tts

_announced = set()
_at_main_menu = False
_game_loaded = False
_shift_done_file = os.path.join(os.path.dirname(__file__), ".shift_done")


def _announce_once(key: str, text: str, interrupt: bool = True):
    if key not in _announced:
        _announced.add(key)
        tts.speak(text, interrupt)
        sdk_logging.info(f"[BL2A11y] Announced: {key}")


def _is_shift_setup_done() -> bool:
    """Check if SHiFT first-time setup has been completed."""
    return os.path.exists(_shift_done_file)


def _mark_shift_done():
    """Mark SHiFT setup as completed so we auto-dismiss next time."""
    try:
        with open(_shift_done_file, "w") as f:
            f.write("done")
        sdk_logging.info("[BL2A11y] Marked SHiFT setup as done")
    except Exception:
        pass


# =============================================================================
# DELAYED PRESS-START DETECTION
# =============================================================================

def _delayed_press_start_check():
    time.sleep(12.0)
    if "main_menu" not in _announced and not _at_main_menu:
        _announce_once("press_start", "Press any key to start.", True)


# =============================================================================
# ONLINE MESSAGE (SHiFT popup)
# =============================================================================

def _on_online_message_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    sdk_logging.info("[BL2A11y] OnlineMessage shown")

    if _is_shift_setup_done():
        # Already done first-time setup — dismiss it
        sdk_logging.info("[BL2A11y] SHiFT already done, dismissing")
        tts.speak("Online popup. Dismissing.", True)
        try:
            obj.Close()
        except Exception:
            pass
        _mark_shift_done()  # Re-mark in case file was deleted
    else:
        # First time — guide the user through it
        tts.speak(
            "Shift account registration screen. "
            "This only appears once. "
            "A sighted person needs to help click Continue, enter a username, and confirm. "
            "After this is done once, it will be skipped automatically on future launches.",
            True
        )


# =============================================================================
# EULA
# =============================================================================

def _on_eula_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    sdk_logging.info("[BL2A11y] EULA shown")
    tts.speak("License agreement. Accepting.", True)
    for method in ['Accept', 'OnAccept', 'Close']:
        try:
            getattr(obj, method)()
            return
        except Exception:
            continue


# =============================================================================
# UPSELL
# =============================================================================

def _on_upsell_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    sdk_logging.info("[BL2A11y] Upsell shown - dismissing")
    tts.speak("Promotional popup. Dismissing.", True)
    try:
        obj.Close()
    except Exception:
        pass


# =============================================================================
# MAIN MENU — announce items, auto-continue
# =============================================================================

def _on_frontend_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    global _at_main_menu
    _at_main_menu = True
    sdk_logging.info("[BL2A11y] Frontend/main menu shown")

    # Mark SHiFT as done since we got past it
    if not _is_shift_setup_done():
        _mark_shift_done()

    tts.speak("Main menu. Loading your saved game in 5 seconds.", True)

    def _auto_continue():
        time.sleep(5.0)
        if not _at_main_menu or _game_loaded:
            return
        sdk_logging.info("[BL2A11y] Auto-continuing...")
        tts.speak("Loading saved game.", True)
        try:
            for movie in unrealsdk.find_all("FrontendGFxMovie", exact=False):
                if movie is None:
                    continue
                try:
                    movie.LaunchSaveGame(0)
                    sdk_logging.info("[BL2A11y] LaunchSaveGame(0) called")
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] LaunchSaveGame(0): {e}")
                try:
                    movie.OpenCharacterSelect()
                    sdk_logging.info("[BL2A11y] OpenCharacterSelect called")
                    tts.speak("Character selection.", True)
                    return
                except Exception as e:
                    sdk_logging.info(f"[BL2A11y] OpenCharacterSelect: {e}")
        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Auto-continue failed: {e}")
    threading.Thread(target=_auto_continue, daemon=True).start()


# =============================================================================
# MAIN MENU ITEM READING — hook into scrolling list focus changes
# =============================================================================

def _on_scrolling_list_focus(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when focus changes in a scrolling list (menu navigation)."""
    try:
        # Try to get the focused item index and text
        idx = -1
        for attr in ['Index', 'ItemIndex', 'SelectedIndex', 'FocusIndex']:
            try:
                val = getattr(args, attr, None)
                if val is not None:
                    idx = int(val)
                    break
            except Exception:
                continue

        sdk_logging.info(f"[BL2A11y] ScrollingList focus: idx={idx}")

        # Main menu items (known order for BL2)
        main_menu_items = [
            "Continue",
            "New Game",
            "Downloadable Content",
            "Mods",
            "Options",
            "Quit",
        ]

        if 0 <= idx < len(main_menu_items):
            tts.speak(main_menu_items[idx], True)
        elif idx >= 0:
            tts.speak(f"Item {idx + 1}", True)
    except Exception as e:
        sdk_logging.info(f"[BL2A11y] ScrollingList focus error: {e}")


def _on_menu_item_click(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a menu item is clicked/selected."""
    try:
        idx = -1
        for attr in ['Index', 'ItemIndex', 'SelectedIndex']:
            try:
                val = getattr(args, attr, None)
                if val is not None:
                    idx = int(val)
                    break
            except Exception:
                continue
        sdk_logging.info(f"[BL2A11y] Menu item clicked: idx={idx}")
    except Exception:
        pass


# =============================================================================
# DIALOG BOXES
# =============================================================================

def _on_dialog_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    sdk_logging.info("[BL2A11y] Dialog shown")
    text = ""
    for attr in ['DialogText', 'MessageText', 'Body', 'Text', 'Description',
                  'sDialog', 'sMessage', 'sBody', 'DialogBody']:
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
            return
        except Exception:
            continue


# =============================================================================
# LOADING / MAP TRANSITIONS
# =============================================================================

def _on_loading_movie(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    tts.speak("Loading.", True)


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    global _at_main_menu, _game_loaded
    _at_main_menu = False
    _game_loaded = True
    _announced.discard("main_menu")
    _announced.discard("press_start")
    tts.speak(
        "Loading complete. "
        "W A S D to move. I J K L to look. Spacebar to fire. F to interact. "
        "F1 health. F2 ammo. F4 full status. F12 stop speech.",
        True
    )


def _on_map_change(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    tts.speak("Loading.", True)


# =============================================================================
# PAUSE, SPLASH
# =============================================================================

def _on_pause_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    tts.speak("Pause menu.", True)


def _on_fullscreen_movie(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    _announce_once("splash", "Loading Borderlands 2.", True)


# =============================================================================
# CONSOLE COMMANDS
# =============================================================================

def _cmd_continue(line: str, cmd_len: int):
    tts.speak("Loading saved game.", True)
    try:
        for m in unrealsdk.find_all("FrontendGFxMovie", exact=False):
            if m is not None:
                try:
                    m.LaunchSaveGame(0)
                    return
                except Exception:
                    pass
    except Exception:
        pass


def _cmd_newgame(line: str, cmd_len: int):
    tts.speak("Starting new game.", True)
    try:
        for m in unrealsdk.find_all("FrontendGFxMovie", exact=False):
            if m is not None:
                try:
                    m.LaunchNewGame()
                    return
                except Exception:
                    pass
    except Exception:
        pass


# =============================================================================
# HOOKS
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
    # Menu navigation — read focused item
    ("WillowGame.FrontendGFxMovie:OnScrollingListItemFocus", hooks.Type.POST, "bl2a11y_menu_focus", _on_scrolling_list_focus),
    ("WillowGame.FrontendGFxMovie:extGenericButtonClicked", hooks.Type.POST, "bl2a11y_menu_click", _on_menu_item_click),
]


def register_hooks():
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
    threading.Thread(target=_delayed_press_start_check, daemon=True).start()
    sdk_logging.info("[BL2A11y Startup] All hooks registered")


def unregister_hooks():
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
