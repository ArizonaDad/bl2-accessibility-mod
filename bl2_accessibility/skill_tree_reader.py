"""
Skill Tree Reader - Reads skill names, descriptions, points, and tiers via TTS.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts


def read_skill_tree() -> str:
    """Read the full skill tree for the current character."""
    try:
        pc = None
        for p in unrealsdk.find_all("WillowPlayerController", exact=False):
            pc = p
            break
        if pc is None:
            return "No player found."

        pawn = pc.Pawn
        if pawn is None:
            return "No character data."

        parts = []

        # Available skill points
        try:
            points = int(pc.GetAvailableSkillPoints()) if hasattr(pc, 'GetAvailableSkillPoints') else 0
            parts.append(f"{points} skill points available")
        except Exception:
            pass

        # Read skill trees
        try:
            skill_manager = pawn.SkillManager if hasattr(pawn, 'SkillManager') else None
            if skill_manager is not None:
                skills = skill_manager.Skills if hasattr(skill_manager, 'Skills') else None
                if skills is not None:
                    for skill in skills:
                        if skill is None:
                            continue
                        try:
                            sdef = skill.Definition if hasattr(skill, 'Definition') else None
                            if sdef is None:
                                continue
                            name = str(sdef.SkillName) if hasattr(sdef, 'SkillName') else ""
                            desc = str(sdef.SkillDescription) if hasattr(sdef, 'SkillDescription') else ""
                            grade = int(skill.Grade) if hasattr(skill, 'Grade') else 0
                            max_grade = int(sdef.MaxGrade) if hasattr(sdef, 'MaxGrade') else 5
                            if name:
                                entry = f"{name}, {grade} of {max_grade} points"
                                if desc:
                                    entry += f". {desc}"
                                parts.append(entry)
                        except Exception:
                            continue
        except Exception:
            pass

        if len(parts) <= 1:
            return "Skill tree. " + (parts[0] if parts else "No skills found.")
        return "Skill tree. " + ". ".join(parts)
    except Exception:
        return "Error reading skill tree."


def _on_skill_tree_open(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when skill tree UI opens."""
    tts.speak("Skill tree.", True)
    # Try to read available points
    try:
        pc = None
        for p in unrealsdk.find_all("WillowPlayerController", exact=False):
            pc = p
            break
        if pc is not None:
            points = int(pc.GetAvailableSkillPoints()) if hasattr(pc, 'GetAvailableSkillPoints') else 0
            if points > 0:
                tts.speak(f"{points} skill points available.", False)
    except Exception:
        pass


def _on_skill_invest(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player invests a skill point."""
    try:
        skill_def = args.Skill if hasattr(args, 'Skill') else None
        if skill_def is None:
            skill_def = args.SkillDef if hasattr(args, 'SkillDef') else None
        if skill_def is not None:
            name = str(skill_def.SkillName) if hasattr(skill_def, 'SkillName') else "Unknown"
            tts.speak(f"Invested point in {name}.", True)
    except Exception:
        tts.speak("Skill point invested.", True)


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all skill tree hooks."""
    hooks.add_hook(
        "WillowGame.WillowPlayerController:InvestSkillPoint",
        hooks.Type.POST, "bl2a11y_skill_invest", _on_skill_invest
    )


def unregister_hooks():
    """Remove all skill tree hooks."""
    hooks.remove_hook("WillowGame.WillowPlayerController:InvestSkillPoint", hooks.Type.POST, "bl2a11y_skill_invest")
