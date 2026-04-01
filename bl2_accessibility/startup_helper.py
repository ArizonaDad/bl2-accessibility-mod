"""
Startup Helper - Handles BL2 startup popups and screens for blind players.

BL2 startup sequence:
1. Splash screens (logos) - auto-skip
2. "Press any key" screen - auto-press or announce
3. EULA/Terms popup - auto-accept or announce
4. SHIFT login popup - dismiss
5. DLC/promo popups - dismiss
6. Main menu arrives

This module hooks into GFxMovie events to detect and handle each popup.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts

_handled_popups = set()


def _try_send_key(key_name: str = "Enter"):
    """Simulate a key press via the player controller."""
    try:
        pc = None
        for p in unrealsdk.find_all("WillowPlayerController", exact=False):
            pc = p
            break
        if pc is None:
            # Try getting from engine
            engine = unrealsdk.find_object("WillowGameEngine", "Transient.WillowGameEngine_0")
            if engine is not None:
                pc = engine.GamePlayers[0].Actor
        if pc is not None:
            pc.ConsoleCommand(f"PressKey {key_name}")
    except Exception:
        pass


def _dismiss_gfx_movie(obj):
    """Try multiple methods to dismiss/accept a GFx movie popup."""
    for method in ['Accept', 'OnAccept', 'AcceptClicked', 'Close', 'OnClose',
                   'CloseDialog', 'DismissDialog', 'OnDismiss', 'ConfirmSelection',
                   'OnConfirm', 'SetExitToMainMenu', 'Dismiss', 'OKClicked',
                   'OnOKClicked', 'ExtClose']:
        try:
            fn = getattr(obj, method, None)
            if fn is not None and callable(fn):
                fn()
                return True
        except Exception:
            continue
    return False


# =============================================================================
# "PRESS ANY KEY" / TITLE SCREEN
# =============================================================================

def _on_press_any_key(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when 'Press Start' / 'Press Any Key' screen shows."""
    popup_id = "press_any_key"
    if popup_id in _handled_popups:
        return
    _handled_popups.add(popup_id)
    tts.speak("Press enter to start.", True)


# =============================================================================
# GENERIC MOVIE START - catch ALL GFxMovie opens
# =============================================================================

def _on_any_movie_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """
    Called when ANY GFxMovie starts. Detect which movie it is and provide TTS.
    This is the broadest hook - catches everything.
    """
    try:
        class_name = str(obj.Class.Name) if obj is not None else ""
        obj_name = str(obj.Name) if obj is not None else ""
        path_name = str(obj._path_name()) if obj is not None else ""

        # Log for debugging
        try:
            from unrealsdk import logging as sdk_logging
            sdk_logging.info(f"[BL2A11y] GFxMovie started: class={class_name} name={obj_name} path={path_name}")
        except Exception:
            pass

        lower_class = class_name.lower()
        lower_name = obj_name.lower()

        # Press Start screen
        if "pressstart" in lower_class or "pressstart" in lower_name or "attractmode" in lower_class:
            tts.speak("Title screen. Press enter to start.", True)
            return

        # EULA / License Agreement
        if "eula" in lower_class or "eula" in lower_name or "license" in lower_class or "agreement" in lower_name:
            tts.speak("License agreement. Press enter to accept.", True)
            return

        # SHIFT login / network
        if "shift" in lower_class or "shift" in lower_name or "sparks" in lower_class:
            tts.speak("Shift login popup. Press escape to skip.", True)
            # Auto-dismiss after a moment
            import threading
            def _auto_dismiss():
                import time
                time.sleep(1.0)
                _dismiss_gfx_movie(obj)
                tts.speak("Skipped.", False)
            threading.Thread(target=_auto_dismiss, daemon=True).start()
            return

        # DLC / Promo / MOTD
        if "dlc" in lower_class or "motd" in lower_class or "promo" in lower_name or "upsell" in lower_name or "offer" in lower_name:
            tts.speak("Promotional popup. Press escape to dismiss.", True)
            return

        # News / MOTD (Message of the Day)
        if "motd" in lower_name or "news" in lower_name or "messageoftheday" in lower_name:
            tts.speak("News popup. Press escape to dismiss.", True)
            return

        # Main menu
        if "frontend" in lower_class or "mainmenu" in lower_class or "frontend" in lower_name:
            tts.speak("Main menu. Continue game, New game, Downloadable content, Mods menu, Options, Quit. Use up and down arrows, press enter to select.", True)
            return

        # Pause menu
        if "pause" in lower_class:
            tts.speak("Pause menu. Resume, Save and Quit. Use up and down arrows, press enter.", True)
            return

        # Character select
        if "character" in lower_class or "charselect" in lower_class or "newgame" in lower_class:
            tts.speak("Character selection. Use left and right arrows to choose. Enter to select.", True)
            return

        # Status menu (inventory/skills)
        if "status" in lower_class or "statusmenu" in lower_class:
            tts.speak("Status menu opened.", True)
            return

        # Vending machine
        if "vending" in lower_class or "vendor" in lower_class:
            tts.speak("Vending machine.", True)
            return

        # Dialog box / confirmation
        if "dialog" in lower_class or "confirmation" in lower_class or "popup" in lower_class or "messagebox" in lower_class:
            tts.speak("Dialog box. Press enter to confirm or escape to cancel.", True)
            return

        # Unknown movie - still announce it
        if class_name and class_name != "GFxMovie":
            friendly = class_name.replace("GFxMovie", "").replace("Gfx", "").replace("Movie", "")
            if friendly:
                tts.speak(f"{friendly} screen opened.", False)

    except Exception as e:
        try:
            from unrealsdk import logging as sdk_logging
            sdk_logging.error(f"[BL2A11y] Error in movie start hook: {e}")
        except Exception:
            pass


# =============================================================================
# PROCESS EVENT HOOK - Catch all input for auto-dismissing stuck screens
# =============================================================================

def _on_any_input(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """
    Very broad input hook - used to detect Enter/Escape presses
    and try to dismiss stuck popups.
    """
    try:
        key = str(args.Key) if hasattr(args, 'Key') else ""
        event = int(args.Event) if hasattr(args, 'Event') else -1

        if event != 0:  # Only on press
            return

        if key == "Enter" or key == "Escape":
            # Try to find and dismiss any active popup/movie
            try:
                for movie in unrealsdk.find_all("GFxMovie", exact=False):
                    if movie is not None:
                        class_name = str(movie.Class.Name).lower()
                        # Don't dismiss gameplay-critical stuff
                        if any(x in class_name for x in ["hud", "loading", "frontend", "pause", "status", "vending"]):
                            continue
                        if any(x in class_name for x in ["eula", "shift", "sparks", "dlc", "motd", "pressstart", "dialog", "popup", "attract"]):
                            _dismiss_gfx_movie(movie)
            except Exception:
                pass
    except Exception:
        pass


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all startup helper hooks."""
    # Broadest possible hook: any GFxMoviePlayer start
    hooks.add_hook(
        "Engine.GFxMoviePlayer:Start",
        hooks.Type.POST, "bl2a11y_any_movie_start", _on_any_movie_start
    )


def unregister_hooks():
    """Remove all startup helper hooks."""
    hooks.remove_hook("Engine.GFxMoviePlayer:Start", hooks.Type.POST, "bl2a11y_any_movie_start")
