"""
Input Manager - Rebinds all controls to keyboard-only layout for blind players.

Movement: WASD
Look/Aim: IJKL (I=up, J=left, K=down, L=right)
Fire: Spacebar
Menus: Arrow keys to navigate, Enter to select, Escape to back

This module injects console commands at game start to rebind all keys
and hooks into input processing to handle the IJKL look system.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts

# Look sensitivity (degrees per tick when holding IJKL)
LOOK_SPEED_YAW = 3.0    # Left/right turn speed
LOOK_SPEED_PITCH = 2.0   # Up/down look speed
_look_state = {"up": False, "down": False, "left": False, "right": False}


def apply_keybindings():
    """
    Apply all keyboard bindings via console commands.
    BL2 uses UE3 keybinding system - we remap everything to keyboard-only.
    """
    pc = _get_pc()
    if pc is None:
        return

    bindings = [
        # Movement - WASD
        ("W", "MoveForward"),
        ("S", "MoveBackward"),
        ("A", "StrafeLeft"),
        ("D", "StrafeRight"),

        # Fire - Spacebar
        ("SpaceBar", "StartFire | OnRelease StopFire"),

        # Aim down sights - Right mouse or alternate key
        ("Q", "StartAltFire | OnRelease StopAltFire"),

        # Reload
        ("R", "ReloadWeapon"),

        # Jump
        ("E", "Jump"),

        # Crouch
        ("C", "Duck | OnRelease UnDuck"),

        # Use/Interact
        ("F", "Use"),

        # Melee
        ("V", "MeleeAttack"),

        # Sprint
        ("LeftShift", "StartSprinting | OnRelease StopSprinting"),

        # Weapon slots
        ("One", "SwitchToWeapon 0"),
        ("Two", "SwitchToWeapon 1"),
        ("Three", "SwitchToWeapon 2"),
        ("Four", "SwitchToWeapon 3"),

        # Grenade
        ("G", "ThrowGrenade"),

        # Action skill
        ("T", "UseActionSkill"),

        # Inventory / menus
        ("Tab", "ShowStatusMenu"),
        ("Escape", "GBA_Pause"),
        ("M", "ToggleMissionLog"),

        # Scroll weapons
        ("MouseScrollUp", "NextWeapon"),
        ("MouseScrollDown", "PrevWeapon"),

        # IJKL - Look controls (handled via input hooks, but bind to prevent conflicts)
        # These are intercepted by our hook system, not passed to default bindings
    ]

    for key, command in bindings:
        try:
            # Use SetBind console command
            pc.ConsoleCommand(f"SetBind {key} {command}")
        except Exception:
            pass


def _get_pc():
    """Get local player controller."""
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


def _process_look():
    """Apply look rotation based on currently held IJKL keys."""
    pc = _get_pc()
    if pc is None:
        return

    try:
        yaw_delta = 0.0
        pitch_delta = 0.0

        if _look_state["left"]:
            yaw_delta -= LOOK_SPEED_YAW
        if _look_state["right"]:
            yaw_delta += LOOK_SPEED_YAW
        if _look_state["up"]:
            pitch_delta += LOOK_SPEED_PITCH
        if _look_state["down"]:
            pitch_delta -= LOOK_SPEED_PITCH

        if yaw_delta != 0.0 or pitch_delta != 0.0:
            # Convert to UE3 rotation units (65536 = 360 degrees)
            yaw_units = int(yaw_delta * (65536.0 / 360.0))
            pitch_units = int(pitch_delta * (65536.0 / 360.0))

            # Get current rotation and modify
            rot = pc.Rotation
            new_yaw = rot.Yaw + yaw_units
            new_pitch = rot.Pitch + pitch_units

            # Clamp pitch to prevent flipping (-16384 to 16384 = -90 to 90 degrees)
            if new_pitch > 16384:
                new_pitch = 16384
            elif new_pitch < -16384:
                new_pitch = -16384

            pc.SetRotation(unrealsdk.make_struct(
                "Core.Object.Rotator",
                Pitch=new_pitch,
                Yaw=new_yaw,
                Roll=0
            ))
    except Exception:
        pass


# =============================================================================
# INPUT HOOKS - Capture IJKL for look control
# =============================================================================

def _on_input_key(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """
    Hook into PlayerInput to capture IJKL keys for look control.
    Called on every key press/release.
    """
    try:
        key_name = str(args.Key) if hasattr(args, 'Key') else ""
        event_type = int(args.Event) if hasattr(args, 'Event') else 0

        # EInputEvent: 0=Pressed, 1=Released, 2=Repeat, 3=DoubleClick
        pressed = event_type == 0 or event_type == 2
        released = event_type == 1

        if key_name == "I":
            if pressed:
                _look_state["up"] = True
            elif released:
                _look_state["up"] = False
            return hooks.Block  # Consume the key

        elif key_name == "K":
            if pressed:
                _look_state["down"] = True
            elif released:
                _look_state["down"] = False
            return hooks.Block

        elif key_name == "J":
            if pressed:
                _look_state["left"] = True
            elif released:
                _look_state["left"] = False
            return hooks.Block

        elif key_name == "L":
            if pressed:
                _look_state["right"] = True
            elif released:
                _look_state["right"] = False
            return hooks.Block

    except Exception:
        pass
    return None  # Don't block other keys


def _on_player_tick(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called every tick - process continuous look input from IJKL."""
    if any(_look_state.values()):
        _process_look()


# =============================================================================
# MENU KEYBOARD NAVIGATION
# =============================================================================

def _on_menu_input(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """
    Hook into GFx menu input to add keyboard navigation.
    Arrow keys = navigate, Enter = select, Escape = back.
    """
    try:
        key_name = str(args.Key) if hasattr(args, 'Key') else ""
        event_type = int(args.Event) if hasattr(args, 'Event') else 0

        if event_type != 0:  # Only on press
            return None

        if key_name == "Up":
            # Simulate moving selection up
            try:
                obj.NavigateUp()
            except Exception:
                try:
                    obj.OnNavigate(-1)
                except Exception:
                    pass
            return hooks.Block

        elif key_name == "Down":
            try:
                obj.NavigateDown()
            except Exception:
                try:
                    obj.OnNavigate(1)
                except Exception:
                    pass
            return hooks.Block

        elif key_name == "Left":
            try:
                obj.NavigateLeft()
            except Exception:
                try:
                    obj.OnNavigateLeft()
                except Exception:
                    pass
            return hooks.Block

        elif key_name == "Right":
            try:
                obj.NavigateRight()
            except Exception:
                try:
                    obj.OnNavigateRight()
                except Exception:
                    pass
            return hooks.Block

        elif key_name == "Enter":
            try:
                obj.AcceptSelection()
            except Exception:
                try:
                    obj.OnAccept()
                except Exception:
                    try:
                        obj.OnSelect()
                    except Exception:
                        pass
            return hooks.Block

        elif key_name == "Escape" or key_name == "BackSpace":
            try:
                obj.GoBack()
            except Exception:
                try:
                    obj.OnCancel()
                except Exception:
                    try:
                        obj.Close()
                    except Exception:
                        pass
            return hooks.Block

    except Exception:
        pass
    return None


# =============================================================================
# GAME START HOOK - Apply bindings when game is ready
# =============================================================================

def _on_game_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when the game world is loaded - apply keybindings."""
    apply_keybindings()
    tts.speak("Controls ready. W A S D to move. I J K L to look. Spacebar to fire. F to interact. Tab for inventory. Escape for menu.", False)


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all input manager hooks."""
    # Player tick for continuous IJKL look processing
    hooks.add_hook(
        "WillowGame.WillowPlayerController:PlayerTick",
        hooks.Type.POST, "bl2a11y_player_tick", _on_player_tick
    )

    # Input key capture for IJKL
    hooks.add_hook(
        "Engine.PlayerInput:InputKey",
        hooks.Type.PRE, "bl2a11y_input_key", _on_input_key
    )

    # Game start - apply bindings
    hooks.add_hook(
        "WillowGame.WillowPlayerController:SpawningProcessComplete",
        hooks.Type.POST, "bl2a11y_spawn_complete", _on_game_start
    )

    # Also apply on map load
    hooks.add_hook(
        "Engine.PlayerController:NotifyLoadedWorld",
        hooks.Type.POST, "bl2a11y_world_loaded", _on_game_start
    )

    # Apply bindings immediately if player already exists
    try:
        apply_keybindings()
    except Exception:
        pass


def unregister_hooks():
    """Remove all input manager hooks."""
    hooks.remove_hook("WillowGame.WillowPlayerController:PlayerTick", hooks.Type.POST, "bl2a11y_player_tick")
    hooks.remove_hook("Engine.PlayerInput:InputKey", hooks.Type.PRE, "bl2a11y_input_key")
    hooks.remove_hook("WillowGame.WillowPlayerController:SpawningProcessComplete", hooks.Type.POST, "bl2a11y_spawn_complete")
    hooks.remove_hook("Engine.PlayerController:NotifyLoadedWorld", hooks.Type.POST, "bl2a11y_world_loaded")

    # Reset look state
    for key in _look_state:
        _look_state[key] = False
