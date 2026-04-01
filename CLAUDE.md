# Borderlands 2 Accessibility Mod for Blind Players

## Project Overview
A comprehensive PythonSDK mod for Borderlands 2 that makes the game fully playable for blind and visually impaired players. Built on the willow2 mod manager (pyunrealsdk/unrealsdk v3.7).

## Architecture
- **Mod framework**: willow2 PythonSDK (pyunrealsdk v1.8.0, unrealsdk v2.0.0)
- **Game**: Borderlands 2 (Unreal Engine 3, Scaleform GFx UI)
- **Install path**: `C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2`
- **SDK mods path**: `{BL2}/sdk_mods/`
- **Project path**: `C:\Users\16239\Documents\bl2-accessibility-mod`
- **Deploy**: Symlink or copy mod folder to `{BL2}/sdk_mods/bl2_accessibility/`

## Mod Structure
```
bl2-accessibility-mod/
├── CLAUDE.md              # This file
├── bl2_accessibility/     # The mod package (deployed to sdk_mods/)
│   ├── __init__.py        # Mod entry point, registers mod with SDK
│   ├── tts.py             # TTS engine (Windows SAPI via comtypes/ctypes)
│   ├── menu_reader.py     # Menu/UI screen reader hooks
│   ├── inventory_reader.py # Inventory/backpack TTS
│   ├── skill_tree_reader.py # Skill tree TTS
│   ├── mission_reader.py  # Mission log TTS
│   ├── vending_reader.py  # Vending machine TTS
│   ├── hud_reader.py      # HUD status readouts (health, shield, ammo, etc.)
│   ├── navigation.py      # Navigation beacons, compass, path assist (future)
│   └── combat.py          # Combat audio, aim assist, enemy radar (future)
├── deploy.py              # Script to symlink/copy mod to BL2 sdk_mods
└── .gitignore
```

## PythonSDK API Reference

### Mod Entry Point
Mods are Python packages in `sdk_mods/`. Each must be a folder with `__init__.py`. The mod manager discovers and imports them automatically.

### New-style Mod (willow2 / mods_base)
```python
from mods_base import build_mod, hook, keybind
```

### Hooks
```python
import unrealsdk
from unrealsdk import hooks

# PRE hook — runs before the function, can block execution
def my_pre_hook(obj, args, ret, func):
    # obj: UObject the function is called on
    # args: WrappedStruct of function arguments
    # ret: return value or previous override
    # func: BoundFunction
    pass  # Return hooks.Block to prevent execution

hooks.add_hook("WillowGame.FrontendGFxMovie:Start", hooks.Type.PRE, "my_id", my_pre_hook)

# POST hook — runs after function completes
hooks.add_hook("WillowGame.WillowHUD:Tick", hooks.Type.POST, "hud_tick", my_post_hook)

# Remove hook
hooks.remove_hook("WillowGame.FrontendGFxMovie:Start", hooks.Type.PRE, "my_id")
```

### Finding Game Objects
```python
import unrealsdk

# Find specific object by class + path
obj = unrealsdk.find_object("WillowGameEngine", "Transient.WillowGameEngine_0")

# Find all instances of a class
for pc in unrealsdk.find_all("WillowPlayerController", exact=False):
    print(pc.Name)

# Find a class
cls = unrealsdk.find_class("WillowInventoryManager")
```

### UObject Property Access
```python
# Properties accessed via attribute syntax
player = unrealsdk.find_all("WillowPlayerController", exact=False).__iter__().__next__()
pawn = player.Pawn
health = pawn.GetHealth()
inv_manager = pawn.InvManager

# Arrays
items = inv_manager.Backpack
for item in items:
    if item is not None:
        print(item.GetShortHumanReadableName())
```

### Console Commands
```python
from unrealsdk import commands

def my_command(line, cmd_len):
    print(f"Command received: {line}")

commands.add_command("mymod", my_command)
```

## Key BL2 Unreal Classes (for menu/UI access)

### Menu System (Scaleform GFx)
- `WillowGame.FrontendGFxMovie` — Main menu
- `WillowGame.PauseGFxMovie` — Pause menu
- `WillowGame.StatusMenuGFxMovie` — Inventory/skills/missions (Tab menu)
- `WillowGame.VendingMachineGFxMovie` — Vending machines
- `WillowGame.CharacterSelectionGFxMovie` — Character select
- `WillowGame.WillowHUD` — In-game HUD
- `WillowGame.TrainingMessageGFxMovie` — Tutorial popups

### Player & Inventory
- `WillowGame.WillowPlayerController` — Player controller (input, camera)
- `WillowGame.WillowPlayerPawn` — Player pawn (health, shield, movement)
- `WillowGame.WillowInventoryManager` — Inventory management
- `WillowGame.WillowWeapon` — Weapon instances
- `WillowGame.WillowItem` — Item instances (shields, grenades, relics, COMs)
- `WillowGame.WillowInventory` — Base inventory item class

### Skills
- `WillowGame.SkillTreeGFxObject` — Skill tree UI
- `WillowGame.SkillDefinition` — Skill definitions
- `WillowGame.SkillTreeBranchDefinition` — Skill tree branches

### Missions
- `WillowGame.MissionTracker` — Active mission tracking
- `WillowGame.MissionDefinition` — Mission definitions

### World
- `WillowGame.WillowGameInfo` — Current game state
- `WillowGame.WillowGameReplicationInfo` — Replicated game state

## TTS Integration Strategy
- Use Windows SAPI via Python `comtypes` or `ctypes` to call `SpVoice`
- Alternatively use `winsound` for simple audio cues
- Speech queue with interrupt support (new speech cancels old)
- Rate/volume configurable via mod options

## Menu Reading Strategy
1. Hook into GFxMovie lifecycle events (Start, Tick, Close)
2. When a menu opens, identify which menu it is
3. Extract text from GFxObject properties or by querying game state
4. Pipe extracted text through TTS
5. Hook into input events to detect navigation (up/down/select) and read the newly focused item

## Development Workflow
1. Edit files in `C:\Users\16239\Documents\bl2-accessibility-mod\bl2_accessibility\`
2. Run `deploy.py` to symlink to `{BL2}/sdk_mods/bl2_accessibility/`
3. Launch BL2 — mod loads automatically
4. Use in-game console (`~` key) for debugging: `py` and `pyexec` commands
5. Check `sdk_mods/settings/` for saved mod options

## Phase 1: Menu Screen Reader (Current Priority)
1. TTS engine integration (Windows SAPI)
2. Main menu / pause menu reading
3. Inventory screen reading (item names, stats, rarity)
4. Skill tree reading
5. Mission log reading
6. Vending machine reading
7. Character select reading

## Phase 2: Navigation (Future)
- Audio beacons on quest objectives
- Audio compass
- Path assist / guide rail
- Environment scanning
- Spatial audio for doors, ledges, hazards

## Phase 3: Combat (Future)
- Lock-on / aim assist with audio feedback
- Enemy spatial audio enhancement
- Audio radar / sonar
- Health/shield ambient tones
- Hit/kill confirmation sounds
- FFYL directional ping

## NVGT Language Notes (from audio moba project)
This project uses Python, not NVGT. But the audio moba project is at `C:\Users\16239\Documents\audio moba\` for reference.
