"""
Mission Reader - Reads mission log, objectives, and quest updates via TTS.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts


def read_active_mission() -> str:
    """Read the currently active mission and its objectives."""
    try:
        pc = None
        for p in unrealsdk.find_all("WillowPlayerController", exact=False):
            pc = p
            break
        if pc is None:
            return "No player controller found."

        # Try to get mission tracker
        tracker = None
        try:
            tracker = pc.MissionTracker if hasattr(pc, 'MissionTracker') else None
        except Exception:
            pass
        if tracker is None:
            try:
                tracker = pc.GetMissionTracker()
            except Exception:
                pass

        if tracker is None:
            return "No mission tracker available."

        # Try to get active missions
        parts = []
        try:
            active_missions = tracker.MissionList if hasattr(tracker, 'MissionList') else None
            if active_missions is not None:
                for mission in active_missions:
                    if mission is None:
                        continue
                    try:
                        mdef = mission.MissionDef if hasattr(mission, 'MissionDef') else None
                        if mdef is None:
                            continue
                        name = str(mdef.MissionName) if hasattr(mdef, 'MissionName') else "Unknown"
                        desc = str(mdef.Description) if hasattr(mdef, 'Description') else ""
                        status = "active"
                        try:
                            s = int(mission.Status) if hasattr(mission, 'Status') else 0
                            if s == 3:
                                status = "ready to turn in"
                            elif s == 4:
                                status = "complete"
                        except Exception:
                            pass

                        entry = f"{name}, {status}"
                        if desc:
                            entry += f". {desc}"
                        parts.append(entry)
                    except Exception:
                        continue
        except Exception:
            pass

        if not parts:
            return "No active missions."
        return "Missions. " + ". ".join(parts)
    except Exception:
        return "Error reading missions."


# =============================================================================
# MISSION EVENT HOOKS
# =============================================================================

def _on_mission_accepted(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a new mission is accepted."""
    try:
        mdef = args.MissionDef if hasattr(args, 'MissionDef') else None
        if mdef is None:
            mdef = args.Mission if hasattr(args, 'Mission') else None
        if mdef is not None:
            name = str(mdef.MissionName) if hasattr(mdef, 'MissionName') else "Unknown mission"
            tts.speak(f"New mission: {name}.", True)
    except Exception:
        tts.speak("New mission accepted.", True)


def _on_mission_complete(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a mission is completed."""
    try:
        mdef = args.MissionDef if hasattr(args, 'MissionDef') else None
        if mdef is None:
            mdef = args.Mission if hasattr(args, 'Mission') else None
        if mdef is not None:
            name = str(mdef.MissionName) if hasattr(mdef, 'MissionName') else "Unknown mission"
            tts.speak(f"Mission complete: {name}.", True)
    except Exception:
        tts.speak("Mission complete.", True)


def _on_objective_update(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a mission objective updates."""
    try:
        text = ""
        try:
            text = str(args.ObjectiveText) if hasattr(args, 'ObjectiveText') else ""
        except Exception:
            pass
        try:
            if not text:
                text = str(args.Description) if hasattr(args, 'Description') else ""
        except Exception:
            pass
        if text:
            tts.speak(f"Objective: {text}", True)
        else:
            tts.speak("Objective updated.", True)
    except Exception:
        pass


def _on_mission_reward(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when mission rewards are given."""
    try:
        xp = int(args.XPReward) if hasattr(args, 'XPReward') else 0
        money = int(args.CurrencyReward) if hasattr(args, 'CurrencyReward') else 0
        parts = []
        if xp > 0:
            parts.append(f"{xp} experience")
        if money > 0:
            parts.append(f"${money}")
        if parts:
            tts.speak("Rewards: " + ", ".join(parts) + ".", False)
    except Exception:
        pass


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all mission reader hooks."""
    hooks.add_hook(
        "WillowGame.WillowPlayerController:AcceptMission",
        hooks.Type.POST, "bl2a11y_mission_accept", _on_mission_accepted
    )

    hooks.add_hook(
        "WillowGame.WillowPlayerController:CompleteMission",
        hooks.Type.POST, "bl2a11y_mission_complete", _on_mission_complete
    )


def unregister_hooks():
    """Remove all mission reader hooks."""
    hooks.remove_hook("WillowGame.WillowPlayerController:AcceptMission", hooks.Type.POST, "bl2a11y_mission_accept")
    hooks.remove_hook("WillowGame.WillowPlayerController:CompleteMission", hooks.Type.POST, "bl2a11y_mission_complete")
