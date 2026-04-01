"""
Startup Helper - Gets blind players through BL2 startup and into the game.

Strategy: Use console commands to bypass Scaleform menus entirely.
BL2's Scaleform menus are mouse-driven Flash and don't respond to keyboard
navigation. Instead of trying to make them accessible, we provide direct
keyboard shortcuts that invoke the game functions via console commands.
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
_press_start_dismissed = False
_at_main_menu = False


def _announce_once(key: str, text: str, interrupt: bool = True):
    """Speak text only once per key."""
    if key not in _announced:
        _announced.add(key)
        tts.speak(text, interrupt)
        sdk_logging.info(f"[BL2A11y Startup] Announced: {key}")


def _get_pc():
    """Get player controller."""
    try:
        engine = unrealsdk.find_object("WillowGameEngine", "Transient.WillowGameEngine_0")
        if engine is not None:
            return engine.GamePlayers[0].Actor
    except Exception:
        pass
    try:
        for pc in unrealsdk.find_all("WillowPlayerController", exact=False):
            return pc
    except Exception:
        pass
    return None


def _console_cmd(cmd: str):
    """Execute a console command."""
    try:
        pc = _get_pc()
        if pc is not None:
            pc.ConsoleCommand(cmd)
            return True
    except Exception:
        pass
    return False


# =============================================================================
# POLLING THREAD
# =============================================================================

def _poll_for_screens():
    """Background thread that detects screens and auto-handles startup."""
    global _polling_active, _press_start_dismissed, _at_main_menu
    sdk_logging.info("[BL2A11y Startup] Polling thread started")

    while _polling_active:
        time.sleep(1.0)
        try:
            active_movies = {}
            try:
                for movie in unrealsdk.find_all("GFxMoviePlayer", exact=False):
                    if movie is None:
                        continue
                    try:
                        cls = str(movie.Class.Name)
                        if "weaponscope" in cls.lower():
                            continue
                        active_movies[cls] = movie
                    except Exception:
                        continue
            except Exception as e:
                sdk_logging.error(f"[BL2A11y Poll] find_all error: {e}")
                continue

            movie_names = set(k.lower() for k in active_movies.keys())
            sdk_logging.info(f"[BL2A11y Poll] Active: {list(active_movies.keys())}")

            # === PRESS START SCREEN ===
            if "willowgfxmoviepressstart" in movie_names:
                if not _press_start_dismissed:
                    _announce_once("press_start", "Press any key to start.", True)
                continue  # Don't process other movies while press-start is up

            # === ONLINE MESSAGE (Shift popup) - appears AFTER pressing start ===
            if "onlinemessagegfxmovie" in movie_names and "frontendgfxmovie" not in movie_names:
                # This is the Shift account popup before main menu
                _announce_once("online_msg", "Online account popup. Skipping automatically.", True)
                movie = active_movies.get("OnlineMessageGFxMovie")
                if movie is not None:
                    # Try every dismiss method aggressively
                    for method in ['Close', 'Accept', 'OnAccept', 'AcceptClicked',
                                   'OKClicked', 'Dismiss', 'OnClose', 'Skip',
                                   'OnSkip', 'Cancel', 'OnCancel']:
                        try:
                            getattr(movie, method)()
                            sdk_logging.info(f"[BL2A11y] OnlineMessage: {method} called")
                        except Exception:
                            pass
                    # Also try clicking via console command
                    _console_cmd("disconnect")  # This can force past stuck screens
                continue

            # === MAIN MENU ===
            if "frontendgfxmovie" in movie_names:
                # Dismiss any overlays first
                if "onlinemessagegfxmovie" in movie_names:
                    movie = active_movies.get("OnlineMessageGFxMovie")
                    if movie is not None:
                        try:
                            movie.Close()
                        except Exception:
                            pass
                if "upsellnotificationgfxmovie" in movie_names:
                    movie = active_movies.get("UpsellNotificationGFxMovie")
                    if movie is not None:
                        try:
                            movie.Close()
                        except Exception:
                            pass

                if not _at_main_menu:
                    _at_main_menu = True
                    _announce_once("main_menu",
                        "Main menu. Press F7 to continue your game. "
                        "Press F8 to start a new game. "
                        "Press escape for options.", True)
                continue

            # === LOADING (no movies active) ===
            if len(active_movies) == 0:
                _announce_once("loading_screen", "Loading.", True)

        except Exception as e:
            sdk_logging.error(f"[BL2A11y Poll] Error: {e}")

    sdk_logging.info("[BL2A11y Startup] Polling thread stopped")


# =============================================================================
# HOOK-BASED DETECTION
# =============================================================================

def _on_frontend_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Main menu movie started."""
    global _at_main_menu
    _at_main_menu = True
    _announce_once("main_menu",
        "Main menu. Press F7 to continue your game. "
        "Press F8 to start a new game. "
        "Press escape for options.", True)


def _on_loading_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Map loaded."""
    _announced.discard("main_menu")
    _announced.discard("loading_screen")
    global _at_main_menu
    _at_main_menu = False
    tts.speak("Loading complete.", True)


def _on_loading_movie(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Loading movie shown."""
    tts.speak("Loading.", True)


def _on_map_change(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Map transition starting."""
    tts.speak("Loading.", True)


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all startup helper hooks."""
    global _polling_active, _poll_thread

    hooks.add_hook(
        "WillowGame.FrontendGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_frontend_start2", _on_frontend_start
    )
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

    # Start polling thread
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
