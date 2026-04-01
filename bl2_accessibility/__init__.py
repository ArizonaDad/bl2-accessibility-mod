"""
BL2 Accessibility Mod - Full screen reader and audio accessibility for blind players.
"""

if True:
    assert __import__("mods_base").__version_info__ >= (1, 4)

from unrealsdk import logging as sdk_logging
sdk_logging.info("[BL2A11y] Module loading...")

from mods_base import build_mod, hook, keybind, EInputEvent, SliderOption, BoolOption

from . import tts
from . import menu_reader
from . import inventory_reader
from . import hud_reader
from . import mission_reader
from . import skill_tree_reader
from . import vending_reader
from . import input_manager
from . import startup_helper

__version__: str = "0.1.0"
__author__: str = "ArizonaDad"


# =============================================================================
# OPTIONS
# =============================================================================

speech_rate = SliderOption(
    "Speech Rate",
    value=3,
    min_value=-10,
    max_value=10,
    step=1,
    description="TTS speech rate. Higher = faster. Default 3.",
)

speech_volume = SliderOption(
    "Speech Volume",
    value=100,
    min_value=0,
    max_value=100,
    step=5,
    description="TTS volume. 0-100.",
)

auto_read_menus = BoolOption(
    "Auto-Read Menus",
    value=True,
    description="Automatically read menu text when menus open.",
)

health_warnings = BoolOption(
    "Health Warnings",
    value=True,
    description="Speak warnings when health or shield is low.",
)

item_pickup_speech = BoolOption(
    "Item Pickup Speech",
    value=True,
    description="Announce items when picked up.",
)

weapon_switch_speech = BoolOption(
    "Weapon Switch Speech",
    value=True,
    description="Announce weapon name and stats when switching weapons.",
)


# =============================================================================
# KEYBINDS
# =============================================================================

@keybind("Read Health and Shield", key="F1", event_filter=EInputEvent.IE_Pressed)
def read_health_key() -> None:
    """Read current health and shield status."""
    text = hud_reader.read_health_shield()
    tts.speak(text, True)


@keybind("Read Ammo", key="F2", event_filter=EInputEvent.IE_Pressed)
def read_ammo_key() -> None:
    """Read current weapon and ammo count."""
    text = hud_reader.read_ammo()
    tts.speak(text, True)


@keybind("Read Level and XP", key="F3", event_filter=EInputEvent.IE_Pressed)
def read_level_key() -> None:
    """Read current level and XP progress."""
    text = hud_reader.read_xp_level()
    tts.speak(text, True)


@keybind("Read Full Status", key="F4", event_filter=EInputEvent.IE_Pressed)
def read_status_key() -> None:
    """Read complete status: health, shield, ammo, level, quest."""
    text = hud_reader.read_full_status()
    tts.speak(text, True)


@keybind("Read Active Mission", key="F5", event_filter=EInputEvent.IE_Pressed)
def read_mission_key() -> None:
    """Read the currently active mission and objectives."""
    text = mission_reader.read_active_mission()
    tts.speak(text, True)


@keybind("Read Skill Tree", key="F6", event_filter=EInputEvent.IE_Pressed)
def read_skills_key() -> None:
    """Read skill tree summary."""
    text = skill_tree_reader.read_skill_tree()
    tts.speak(text, True)


@keybind("Continue Game", key="F7", event_filter=EInputEvent.IE_Pressed)
def continue_game_key() -> None:
    """Continue most recent save / dismiss any popup."""
    import unrealsdk as usdk
    tts.speak("Continuing game.", True)
    # First try to dismiss any blocking popups
    try:
        for movie in usdk.find_all("GFxMoviePlayer", exact=False):
            if movie is None:
                continue
            cls = str(movie.Class.Name).lower()
            if any(x in cls for x in ["onlinemessage", "upsell", "dialog", "training"]):
                for m in ['Close', 'Accept', 'OnAccept', 'AcceptClicked', 'OKClicked', 'Dismiss']:
                    try:
                        getattr(movie, m)()
                    except Exception:
                        pass
    except Exception:
        pass
    # Try to invoke continue on the frontend
    try:
        for movie in usdk.find_all("FrontendGFxMovie", exact=False):
            if movie is None:
                continue
            # Try multiple ways to start continue
            for method in ['ContinueGame', 'OnContinueGame', 'LaunchContinue',
                           'SelectContinue', 'PlayGame', 'OnPlayGame']:
                try:
                    getattr(movie, method)()
                    sdk_logging.info(f"[BL2A11y] Continue via {method}")
                    return
                except Exception:
                    pass
    except Exception:
        pass
    # Fallback: use console command to load into the game
    try:
        pc = hud_reader.get_player_controller()
        if pc is not None:
            pc.ConsoleCommand("open menudefaultmap")
    except Exception:
        pass


@keybind("New Game", key="F8", event_filter=EInputEvent.IE_Pressed)
def new_game_key() -> None:
    """Start a new game from main menu."""
    import unrealsdk as usdk
    tts.speak("Starting new game.", True)
    try:
        for movie in usdk.find_all("FrontendGFxMovie", exact=False):
            if movie is None:
                continue
            for method in ['NewGame', 'OnNewGame', 'LaunchNewGame', 'SelectNewGame',
                           'StartNewGame', 'OnStartNewGame']:
                try:
                    getattr(movie, method)()
                    sdk_logging.info(f"[BL2A11y] New game via {method}")
                    return
                except Exception:
                    pass
    except Exception:
        pass


@keybind("Stop Speech", key="F12", event_filter=EInputEvent.IE_Pressed)
def stop_speech_key() -> None:
    """Stop all current TTS speech."""
    tts.stop()


# =============================================================================
# MOD LIFECYCLE
# =============================================================================

def on_enable() -> None:
    """Called when the mod is enabled."""
    sdk_logging.info("[BL2A11y] on_enable called")
    tts.init()
    tts.set_rate(speech_rate.value)
    tts.set_volume(speech_volume.value)
    startup_helper.register_hooks()
    input_manager.register_hooks()
    menu_reader.register_hooks()
    inventory_reader.register_hooks()
    hud_reader.register_hooks()
    mission_reader.register_hooks()
    skill_tree_reader.register_hooks()
    vending_reader.register_hooks()
    sdk_logging.info("[BL2A11y] All hooks registered")
    tts.speak("BL2 Accessibility Mod enabled.", True)


def on_disable() -> None:
    """Called when the mod is disabled."""
    startup_helper.unregister_hooks()
    input_manager.unregister_hooks()
    menu_reader.unregister_hooks()
    inventory_reader.unregister_hooks()
    hud_reader.unregister_hooks()
    mission_reader.unregister_hooks()
    skill_tree_reader.unregister_hooks()
    vending_reader.unregister_hooks()
    tts.speak("BL2 Accessibility Mod disabled.", True)
    tts.shutdown()


# =============================================================================
# BUILD MOD
# =============================================================================

mod = build_mod(
    name="BL2 Accessibility",
    description="Full screen reader and audio accessibility for blind players. TTS for all menus, inventory, skills, missions, HUD, and combat alerts.",
    auto_enable=True,
)

# =============================================================================
# FORCE-ENABLE ON FIRST LOAD
# =============================================================================
# Accessibility mods MUST work immediately - blind players cannot navigate
# the Mods menu to enable it manually. Force-enable at import time so TTS
# starts the moment the game launches. auto_enable=True handles subsequent loads,
# but this handles the very first install.

sdk_logging.info("[BL2A11y] Mod built, attempting force-enable...")
try:
    if not mod.is_enabled:
        sdk_logging.info("[BL2A11y] Mod not enabled, calling mod.enable()")
        mod.enable()
    else:
        sdk_logging.info("[BL2A11y] Mod already enabled")
except Exception as e:
    sdk_logging.error(f"[BL2A11y] mod.enable() failed: {e}")
    try:
        sdk_logging.info("[BL2A11y] Falling back to direct on_enable()")
        on_enable()
    except Exception as e2:
        sdk_logging.error(f"[BL2A11y] on_enable() also failed: {e2}")
