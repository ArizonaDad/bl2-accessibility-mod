"""
HUD Reader - Reads health, shield, ammo, XP, level, and combat status via TTS.
Provides hotkey-based readouts and automatic alerts for critical events.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts

# Tracking for change detection
_last_health_pct = 100
_last_shield_pct = 100
_warned_low_health = False
_warned_low_shield = False
_in_ffyl = False


def get_player_controller():
    """Get the local player controller."""
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


def get_player_pawn():
    """Get the local player pawn."""
    pc = get_player_controller()
    if pc is not None:
        try:
            return pc.Pawn
        except Exception:
            pass
    return None


def read_health_shield() -> str:
    """Read current health and shield values."""
    pawn = get_player_pawn()
    if pawn is None:
        return "No player data available."
    parts = []
    try:
        health = int(pawn.GetHealth())
        max_health = int(pawn.GetMaxHealth())
        parts.append(f"Health {health} of {max_health}")
    except Exception:
        parts.append("Health unknown")

    try:
        shield = int(pawn.GetShieldStrength())
        max_shield = int(pawn.GetMaxShieldStrength())
        parts.append(f"Shield {shield} of {max_shield}")
    except Exception:
        pass

    return ". ".join(parts)


def read_ammo() -> str:
    """Read current weapon ammo."""
    pawn = get_player_pawn()
    if pawn is None:
        return "No weapon data."
    try:
        weapon = pawn.Weapon
        if weapon is None:
            return "No weapon equipped."
        clip = int(weapon.AmmoInClip) if hasattr(weapon, 'AmmoInClip') else 0
        # Try to get reserve ammo
        reserve = ""
        try:
            ammo_pool = weapon.AmmoPool if hasattr(weapon, 'AmmoPool') else None
            if ammo_pool is not None:
                total = int(ammo_pool.GetCurrentValue()) if hasattr(ammo_pool, 'GetCurrentValue') else 0
                reserve = f", {total} reserve"
        except Exception:
            pass
        name = str(weapon.GetShortHumanReadableName())
        return f"{name}. {clip} in magazine{reserve}."
    except Exception:
        return "Ammo unknown."


def read_xp_level() -> str:
    """Read XP and level info."""
    pc = get_player_controller()
    if pc is None:
        return "No player data."
    try:
        pri = pc.PlayerReplicationInfo
        level = int(pri.ExpLevel) if hasattr(pri, 'ExpLevel') else 0
        xp = int(pri.ExpPoints) if hasattr(pri, 'ExpPoints') else 0
        next_xp = int(pri.ExpPointsForNextLevel) if hasattr(pri, 'ExpPointsForNextLevel') else 0
        return f"Level {level}. Experience {xp} of {next_xp}."
    except Exception:
        return "Level unknown."


def read_full_status() -> str:
    """Read complete status: health, shield, ammo, level."""
    parts = []
    parts.append(read_health_shield())
    parts.append(read_ammo())
    parts.append(read_xp_level())

    # Active quest
    try:
        pc = get_player_controller()
        if pc is not None:
            tracker = pc.GetMissionTracker() if hasattr(pc, 'GetMissionTracker') else None
            if tracker is not None:
                active = tracker.GetActiveMission() if hasattr(tracker, 'GetActiveMission') else None
                if active is not None:
                    mission_name = str(active.MissionName) if hasattr(active, 'MissionName') else ""
                    if mission_name:
                        parts.append(f"Active quest: {mission_name}")
    except Exception:
        pass

    return " ".join(parts)


# =============================================================================
# AUTOMATIC ALERTS (health/shield warnings, FFYL, level up)
# =============================================================================

def _on_hud_tick(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Periodic HUD tick to check for status changes."""
    global _last_health_pct, _last_shield_pct, _warned_low_health, _warned_low_shield
    try:
        pawn = get_player_pawn()
        if pawn is None:
            return

        # Health check
        try:
            health = pawn.GetHealth()
            max_health = pawn.GetMaxHealth()
            if max_health > 0:
                pct = int((health / max_health) * 100)
                if pct <= 25 and not _warned_low_health:
                    _warned_low_health = True
                    tts.speak("Low health!", True)
                elif pct <= 10 and _warned_low_health and _last_health_pct > 10:
                    tts.speak("Health critical!", True)
                elif pct > 30:
                    _warned_low_health = False
                _last_health_pct = pct
        except Exception:
            pass

        # Shield check
        try:
            shield = pawn.GetShieldStrength()
            max_shield = pawn.GetMaxShieldStrength()
            if max_shield > 0:
                pct = int((shield / max_shield) * 100)
                if pct <= 0 and not _warned_low_shield:
                    _warned_low_shield = True
                    tts.speak("Shield depleted!", False)
                elif pct > 10:
                    _warned_low_shield = False
                _last_shield_pct = pct
        except Exception:
            pass
    except Exception:
        pass


def _on_ffyl_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when Fight For Your Life starts."""
    global _in_ffyl
    _in_ffyl = True
    tts.speak("Fight for your life! Get a kill for second wind!", True)


def _on_ffyl_end(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when FFYL ends (revive or death)."""
    global _in_ffyl
    _in_ffyl = False


def _on_second_wind(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called on second wind."""
    global _in_ffyl
    _in_ffyl = False
    tts.speak("Second wind!", True)


def _on_player_death(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called on player death."""
    global _in_ffyl
    _in_ffyl = False
    tts.speak("You died. Respawning.", True)


def _on_level_up(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player levels up."""
    try:
        pc = get_player_controller()
        if pc is not None:
            pri = pc.PlayerReplicationInfo
            level = int(pri.ExpLevel) if hasattr(pri, 'ExpLevel') else 0
            tts.speak(f"Level up! You are now level {level}.", True)
    except Exception:
        tts.speak("Level up!", True)


def _on_kill(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player kills an enemy."""
    try:
        if _in_ffyl:
            tts.speak("Second wind!", True)
    except Exception:
        pass


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all HUD reader hooks."""
    # Level up
    hooks.add_hook(
        "WillowGame.WillowPlayerController:LevelUp",
        hooks.Type.POST, "bl2a11y_level_up", _on_level_up
    )

    # FFYL
    hooks.add_hook(
        "WillowGame.WillowPlayerPawn:StartInjuredState",
        hooks.Type.POST, "bl2a11y_ffyl_start", _on_ffyl_start
    )

    # Death
    hooks.add_hook(
        "WillowGame.WillowPlayerPawn:Died",
        hooks.Type.POST, "bl2a11y_death", _on_player_death
    )


def unregister_hooks():
    """Remove all HUD reader hooks."""
    hooks.remove_hook("WillowGame.WillowPlayerController:LevelUp", hooks.Type.POST, "bl2a11y_level_up")
    hooks.remove_hook("WillowGame.WillowPlayerPawn:StartInjuredState", hooks.Type.POST, "bl2a11y_ffyl_start")
    hooks.remove_hook("WillowGame.WillowPlayerPawn:Died", hooks.Type.POST, "bl2a11y_death")
