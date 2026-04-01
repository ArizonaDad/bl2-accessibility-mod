"""
Menu Reader - Hooks into BL2 Scaleform GFx menus and reads text via TTS.
Handles: Main menu, Pause menu, character select, and general menu navigation.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts


# Track current menu state
_current_menu = ""
_last_spoken = ""


def _speak_once(text: str, interrupt: bool = True):
    """Only speak if text differs from last spoken."""
    global _last_spoken
    if text and text != _last_spoken:
        _last_spoken = text
        tts.speak(text, interrupt)


# =============================================================================
# MAIN MENU (FrontendGFxMovie)
# =============================================================================

def _on_frontend_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when main menu opens."""
    global _current_menu
    _current_menu = "main_menu"
    tts.speak("Main menu. Use up and down arrows to navigate. Enter to select.", True)


def _on_frontend_input(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called on input in the frontend menu. Read the focused item."""
    try:
        # Try to get the currently selected menu item text
        _read_current_menu_item(obj, "main_menu")
    except Exception:
        pass


# =============================================================================
# PAUSE MENU (PauseGFxMovie)
# =============================================================================

def _on_pause_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when pause menu opens."""
    global _current_menu
    _current_menu = "pause_menu"
    tts.speak("Pause menu.", True)


def _on_pause_closed(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when pause menu closes."""
    global _current_menu
    if _current_menu == "pause_menu":
        _current_menu = ""
        tts.speak("Resumed.", True)


# =============================================================================
# CHARACTER SELECT
# =============================================================================

def _on_charsel_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when character selection screen opens."""
    global _current_menu
    _current_menu = "character_select"
    tts.speak("Character selection. Use left and right to browse characters. Enter to select.", True)


# =============================================================================
# LOADING SCREEN
# =============================================================================

def _on_loading_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a loading screen appears."""
    tts.speak("Loading.", True)


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when loading finishes."""
    tts.speak("Loading complete.", True)


# =============================================================================
# DIALOG / POPUP BOXES
# =============================================================================

def _on_dialog_box(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a dialog/popup appears. Read its text."""
    try:
        # Try to read dialog title and body
        title = ""
        body = ""
        try:
            title = str(args.Title) if hasattr(args, 'Title') else ""
        except Exception:
            pass
        try:
            body = str(args.Body) if hasattr(args, 'Body') else ""
        except Exception:
            pass
        try:
            body = str(args.Message) if hasattr(args, 'Message') else body
        except Exception:
            pass

        text = ""
        if title:
            text = title
        if body:
            text = text + ". " + body if text else body
        if text:
            tts.speak("Dialog. " + text, True)
    except Exception:
        tts.speak("Dialog box opened.", True)


# =============================================================================
# TRAINING / TUTORIAL MESSAGES
# =============================================================================

def _on_training_message(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a training/tutorial popup appears."""
    try:
        header = ""
        body = ""
        try:
            header = str(obj.Header) if hasattr(obj, 'Header') else ""
        except Exception:
            pass
        try:
            body = str(obj.Body) if hasattr(obj, 'Body') else ""
        except Exception:
            pass
        try:
            body = str(obj.MessageBody) if hasattr(obj, 'MessageBody') else body
        except Exception:
            pass

        text = ""
        if header:
            text = header
        if body:
            text = text + ". " + body if text else body
        if text:
            tts.speak("Tutorial. " + text, True)
    except Exception:
        pass


# =============================================================================
# GENERAL: Intercept ANY GFxMovie text setting for universal TTS
# =============================================================================

def _on_set_text(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """
    Hook into SetText calls on GFx objects to read ALL text changes.
    This is a broad hook that catches text updates across all menus.
    """
    try:
        text = str(args.Text) if hasattr(args, 'Text') else ""
        if not text:
            text = str(args.S) if hasattr(args, 'S') else ""
        if text and len(text) > 1 and text != _last_spoken:
            # Filter out common noise (numbers, single chars, etc.)
            stripped = text.strip()
            if stripped and not stripped.isdigit() and len(stripped) > 2:
                _speak_once(stripped, False)
    except Exception:
        pass


# =============================================================================
# GENERAL: Menu item selection feedback
# =============================================================================

def _on_menu_item_select(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a menu item is focused/selected."""
    try:
        # Try multiple common property names for the selected item text
        for attr in ('ItemName', 'MenuItemLabel', 'Label', 'Text', 'Caption', 'Title', 'Name'):
            try:
                val = getattr(obj, attr, None)
                if val is not None:
                    text = str(val).strip()
                    if text:
                        _speak_once(text, True)
                        return
            except Exception:
                continue
    except Exception:
        pass


def _read_current_menu_item(gfx_movie, menu_name: str):
    """Try to read the current focused item in a GFx menu."""
    try:
        # Attempt to get selected index and item text from the GFx movie
        for attr in ('CurrentSelection', 'SelectedIndex', 'FocusedIndex'):
            try:
                idx = getattr(gfx_movie, attr, None)
                if idx is not None:
                    break
            except Exception:
                continue
    except Exception:
        pass


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all menu reader hooks."""
    # Main menu
    hooks.add_hook(
        "WillowGame.FrontendGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_frontend_start", _on_frontend_start
    )

    # Pause menu
    hooks.add_hook(
        "WillowGame.PauseGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_pause_start", _on_pause_start
    )

    # Character select
    hooks.add_hook(
        "WillowGame.CharacterSelectionReduxGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_charsel_start", _on_charsel_start
    )

    # Training/tutorial messages
    hooks.add_hook(
        "WillowGame.WillowHUD:DisplayTrainingMessage",
        hooks.Type.POST, "bl2a11y_training", _on_training_message
    )

    # Loading screens
    hooks.add_hook(
        "Engine.PlayerController:NotifyLoadedWorld",
        hooks.Type.POST, "bl2a11y_loaded", _on_loading_complete
    )


def unregister_hooks():
    """Remove all menu reader hooks."""
    hooks.remove_hook("WillowGame.FrontendGFxMovie:Start", hooks.Type.POST, "bl2a11y_frontend_start")
    hooks.remove_hook("WillowGame.PauseGFxMovie:Start", hooks.Type.POST, "bl2a11y_pause_start")
    hooks.remove_hook("WillowGame.CharacterSelectionReduxGFxMovie:Start", hooks.Type.POST, "bl2a11y_charsel_start")
    hooks.remove_hook("WillowGame.WillowHUD:DisplayTrainingMessage", hooks.Type.POST, "bl2a11y_training")
    hooks.remove_hook("Engine.PlayerController:NotifyLoadedWorld", hooks.Type.POST, "bl2a11y_loaded")
