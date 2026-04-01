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
_pending_action = -1  # Menu item index to activate on main thread


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

def _lower_game_volume():
    """Lower game volume by modifying profile settings. Safe approach."""
    try:
        # Wait for game to be ready
        time.sleep(3.0)
        for pc in unrealsdk.find_all("WillowPlayerController", exact=False):
            if pc is None:
                continue
            try:
                # Use profile settings (WPS = Willow Profile Setting)
                profile = pc.GetCachedProfileSettings()
                if profile is not None:
                    # These are profile setting IDs for volume
                    # WPS_MasterVolume, WPS_SFXVolume, WPS_MusicVolume, WPS_VOVolume
                    for attr in ['MasterVolume', 'SFXVolume', 'MusicVolume']:
                        try:
                            # Try setting directly
                            setattr(profile, attr, 0.3)
                        except Exception:
                            pass
                sdk_logging.info("[BL2A11y] Attempted volume lower via profile")
            except Exception:
                pass
            break
    except Exception as e:
        sdk_logging.info(f"[BL2A11y] Volume lower failed: {e}")


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

    tts.speak(
        "Main menu. Use W and S to navigate. Press enter to select.",
        True
    )

    # Try to read the actual menu items by probing the movie's Flash variables
    def _probe_menu():
        time.sleep(1.0)
        try:
            # Try to read menu state via GetVariable on the Flash movie
            for attr in ['GetVariableString', 'GetVariable', 'GetVariableObject']:
                try:
                    fn = getattr(obj, attr, None)
                    if fn is not None:
                        # Common Flash paths for menu items
                        for path in ['_root.MenuList.selectedIndex',
                                     '_root.MenuPanel.selectedIndex',
                                     'MenuList.selectedIndex',
                                     'selectedIndex']:
                            try:
                                val = fn(path)
                                sdk_logging.info(f"[BL2A11y] Flash {attr}({path}) = {val}")
                            except Exception:
                                pass
                except Exception:
                    pass

            # Log all properties we can find on the movie for debugging
            try:
                for prop in ['TheList', 'FrontendMenu', 'CurrentSelectedDifficulty']:
                    try:
                        val = getattr(obj, prop, None)
                        if val is not None:
                            sdk_logging.info(f"[BL2A11y] Frontend.{prop} = {val} (type: {type(val).__name__})")
                    except Exception as e:
                        sdk_logging.info(f"[BL2A11y] Frontend.{prop}: {e}")
            except Exception:
                pass
        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Menu probe error: {e}")
    threading.Thread(target=_probe_menu, daemon=True).start()

    # Start keyboard navigation thread (uses GetAsyncKeyState for raw keyboard)
    threading.Thread(target=_menu_keyboard_thread, daemon=True).start()


# =============================================================================
# MAIN MENU ITEM READING — hook into scrolling list focus changes
# =============================================================================

_menu_index = 0
_menu_items = ["Continue", "New Game", "Downloadable Content", "Mods", "Options", "Quit"]
_menu_item_count = 6

def _set_menu_index(movie, idx):
    """Set the Flash menu selection index and announce it."""
    global _menu_index
    if idx < 0:
        idx = _menu_item_count - 1
    if idx >= _menu_item_count:
        idx = 0
    _menu_index = idx

    # Set the Flash variable to move the visual selection
    try:
        movie.SetVariableNumber("_root.FrontendMenu.TheList.selectedIndex", float(idx))
    except Exception as e:
        sdk_logging.info(f"[BL2A11y] SetVariableNumber failed: {e}")

    # Also try ActionScriptVoid to call gotoAndStop or similar
    try:
        movie.ActionScriptVoid("_root.FrontendMenu.TheList.InvalidateData")
    except Exception:
        pass

    # Announce the item
    if idx < len(_menu_items):
        tts.speak(_menu_items[idx], True)
    else:
        tts.speak(f"Item {idx + 1}", True)
    sdk_logging.info(f"[BL2A11y] Menu selection set to {idx}: {_menu_items[idx] if idx < len(_menu_items) else 'unknown'}")


def _activate_menu_item(movie, idx):
    """Queue a menu activation — must execute on main thread via tick hook."""
    global _pending_action
    sdk_logging.info(f"[BL2A11y] Queuing menu action {idx}")
    _pending_action = idx

    if idx == 0:
        tts.speak("Loading saved game.", True)
    elif idx == 1:
        tts.speak("Starting new game.", True)
    elif idx == 2:
        tts.speak("Downloadable content.", True)
    elif idx == 3:
        tts.speak("Mods menu.", True)
    elif idx == 4:
        tts.speak("Options.", True)
    elif idx == 5:
        tts.speak("Quitting game.", True)


def _execute_pending_action():
    """Execute queued menu action on main game thread. Called from tick hook."""
    global _pending_action, _at_main_menu
    if _pending_action < 0:
        return
    idx = _pending_action
    _pending_action = -1
    sdk_logging.info(f"[BL2A11y] Executing menu action {idx} on main thread")

    try:
        movie = None
        for m in unrealsdk.find_all("FrontendGFxMovie", exact=False):
            if m is not None:
                movie = m
                break
        if movie is None:
            sdk_logging.error("[BL2A11y] No FrontendGFxMovie found")
            return

        if idx == 0:
            try:
                movie.LaunchSaveGame(0)
                sdk_logging.info("[BL2A11y] LaunchSaveGame(0) called on main thread")
            except Exception as e:
                sdk_logging.info(f"[BL2A11y] LaunchSaveGame: {e}")
                try:
                    movie.OpenCharacterSelect()
                except Exception:
                    pass
        elif idx == 1:
            try:
                movie.LaunchNewGame()
                sdk_logging.info("[BL2A11y] LaunchNewGame called on main thread")
            except Exception as e:
                sdk_logging.info(f"[BL2A11y] LaunchNewGame: {e}")
                try:
                    movie.OpenCharacterSelect()
                except Exception:
                    pass
        elif idx == 4:
            try:
                movie.ShowOptions()
                sdk_logging.info("[BL2A11y] ShowOptions called on main thread")
            except Exception as e:
                sdk_logging.info(f"[BL2A11y] ShowOptions: {e}")
        elif idx == 5:
            try:
                movie.ConfirmQuit_Clicked()
                sdk_logging.info("[BL2A11y] ConfirmQuit called on main thread")
            except Exception as e:
                sdk_logging.info(f"[BL2A11y] ConfirmQuit: {e}")
    except Exception as e:
        sdk_logging.error(f"[BL2A11y] Execute action error: {e}")


def _on_tick(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Main thread tick — execute any pending menu actions."""
    if _pending_action >= 0:
        _execute_pending_action()


def _menu_keyboard_thread():
    """Thread that polls keyboard state to navigate the main menu."""
    global _menu_index, _at_main_menu
    import ctypes
    import ctypes.wintypes
    user32 = ctypes.windll.user32
    user32.GetAsyncKeyState.restype = ctypes.wintypes.SHORT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

    # Virtual key codes
    VK_UP = 0x26
    VK_DOWN = 0x28
    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B
    VK_W = 0x57
    VK_S = 0x53

    # Also set up GetKeyboardState for arrow keys (Scaleform eats them from GetAsyncKeyState)
    keyboard_state = (ctypes.c_ubyte * 256)()

    def _is_key_down(vk):
        """Check if key is down using both methods."""
        # Method 1: GetAsyncKeyState
        if user32.GetAsyncKeyState(vk) & 0x8000:
            return True
        # Method 2: GetKeyboardState (catches keys Scaleform consumed)
        user32.GetKeyboardState(keyboard_state)
        if keyboard_state[vk] & 0x80:
            return True
        return False

    sdk_logging.info("[BL2A11y] Menu keyboard thread started")

    # Announce initial selection
    time.sleep(0.5)
    tts.speak("Continue. Use up and down arrows to navigate. Enter to select.", True)

    last_up = False
    last_down = False
    last_enter = False
    log_counter = 0

    while _at_main_menu and not _game_loaded:
        time.sleep(0.05)  # 50ms poll = responsive
        try:
            up_pressed = _is_key_down(VK_UP) or _is_key_down(VK_W)
            down_pressed = _is_key_down(VK_DOWN) or _is_key_down(VK_S)
            enter_pressed = _is_key_down(VK_RETURN)

            # Log any key press
            if up_pressed and not last_up:
                sdk_logging.info("[BL2A11y] UP detected")
            if down_pressed and not last_down:
                sdk_logging.info("[BL2A11y] DOWN detected")
            if enter_pressed and not last_enter:
                sdk_logging.info("[BL2A11y] ENTER detected")

            movie = None
            for m in unrealsdk.find_all("FrontendGFxMovie", exact=False):
                if m is not None:
                    movie = m
                    break

            if movie is None:
                continue

            # Up arrow — move selection up
            if up_pressed and not last_up:
                _set_menu_index(movie, _menu_index - 1)

            # Down arrow — move selection down
            if down_pressed and not last_down:
                _set_menu_index(movie, _menu_index + 1)

            # Enter — activate
            if enter_pressed and not last_enter:
                _activate_menu_item(movie, _menu_index)

            last_up = up_pressed
            last_down = down_pressed
            last_enter = enter_pressed

        except Exception as e:
            sdk_logging.error(f"[BL2A11y] Menu keyboard error: {e}")
            time.sleep(1.0)

    sdk_logging.info("[BL2A11y] Menu keyboard thread ended")


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
    # Tick hook for executing menu actions on main thread
    ("Engine.GameViewportClient:Tick", hooks.Type.POST, "bl2a11y_tick", _on_tick),
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
    threading.Thread(target=_lower_game_volume, daemon=True).start()
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
