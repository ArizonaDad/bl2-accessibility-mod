"""
Inventory Reader - Reads weapon/item stats, rarity, and details via TTS.
Covers: Backpack, equipped items, item cards, item pickup, and comparison.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts


# Rarity names by index
RARITY_NAMES = {
    0: "white, common",
    1: "green, uncommon",
    2: "blue, rare",
    3: "purple, very rare",
    4: "orange, legendary",
    5: "magenta, e-tech",
    6: "cyan, seraph",
    7: "pink, effervescent",
    8: "pearl, pearlescent",
}

_last_item_spoken = ""


def get_rarity_name(rarity_level: int) -> str:
    """Get human-readable rarity from numeric level."""
    return RARITY_NAMES.get(rarity_level, f"rarity {rarity_level}")


def read_weapon_stats(weapon) -> str:
    """Build a full TTS string for a weapon."""
    parts = []
    try:
        # Name
        name = ""
        try:
            name = str(weapon.GetShortHumanReadableName())
        except Exception:
            try:
                name = str(weapon.GetHumanReadableName())
            except Exception:
                name = "Unknown weapon"
        parts.append(name)

        # Rarity
        try:
            rarity = int(weapon.RarityLevel)
            parts.append(get_rarity_name(rarity))
        except Exception:
            pass

        # Level
        try:
            level = int(weapon.ExpLevel) if hasattr(weapon, 'ExpLevel') else None
            if level is not None:
                parts.append(f"level {level}")
        except Exception:
            pass

        # Type (pistol, shotgun, etc.)
        try:
            wtype = str(weapon.DefinitionData.WeaponTypeDefinition.Name)
            parts.append(wtype)
        except Exception:
            pass

        # Damage
        try:
            dmg = weapon.GetDamage() if hasattr(weapon, 'GetDamage') else None
            if dmg is not None:
                parts.append(f"{int(dmg)} damage")
        except Exception:
            pass

        # Fire rate
        try:
            fr = weapon.GetFireRate() if hasattr(weapon, 'GetFireRate') else None
            if fr is not None:
                parts.append(f"{fr:.1f} fire rate")
        except Exception:
            pass

        # Reload speed
        try:
            rs = weapon.GetReloadSpeed() if hasattr(weapon, 'GetReloadSpeed') else None
            if rs is not None:
                parts.append(f"{rs:.1f} second reload")
        except Exception:
            pass

        # Magazine size
        try:
            mag = weapon.GetMagazineSize() if hasattr(weapon, 'GetMagazineSize') else None
            if mag is not None:
                parts.append(f"{int(mag)} magazine")
        except Exception:
            pass

        # Element
        try:
            elem = weapon.GetElementalType() if hasattr(weapon, 'GetElementalType') else None
            if elem is not None and elem != 0:
                elem_names = {1: "fire", 2: "shock", 3: "corrosive", 4: "slag", 5: "explosive"}
                parts.append(elem_names.get(elem, f"element {elem}"))
        except Exception:
            pass

        # Manufacturer
        try:
            mfr = str(weapon.DefinitionData.ManufacturerDefinition.Name)
            if mfr and mfr != "None":
                parts.append(f"by {mfr}")
        except Exception:
            pass

    except Exception:
        parts.append("Error reading weapon")

    return ", ".join(parts)


def read_item_stats(item) -> str:
    """Build a TTS string for a non-weapon item (shield, grenade, relic, COM)."""
    parts = []
    try:
        # Name
        name = ""
        try:
            name = str(item.GetShortHumanReadableName())
        except Exception:
            try:
                name = str(item.GetHumanReadableName())
            except Exception:
                name = "Unknown item"
        parts.append(name)

        # Rarity
        try:
            rarity = int(item.RarityLevel)
            parts.append(get_rarity_name(rarity))
        except Exception:
            pass

        # Level
        try:
            level = int(item.ExpLevel) if hasattr(item, 'ExpLevel') else None
            if level is not None:
                parts.append(f"level {level}")
        except Exception:
            pass

        # Type-specific stats
        try:
            # Shield capacity
            cap = getattr(item, 'GetShieldStrength', None)
            if cap is not None:
                parts.append(f"{int(cap())} shield capacity")
        except Exception:
            pass

        try:
            # Grenade damage
            gdmg = getattr(item, 'GetGrenadeDamage', None)
            if gdmg is not None:
                parts.append(f"{int(gdmg())} grenade damage")
        except Exception:
            pass

    except Exception:
        parts.append("Error reading item")

    return ", ".join(parts)


def read_inventory_item(item) -> str:
    """Read any inventory item, detecting type automatically."""
    if item is None:
        return "Empty slot"
    try:
        cls_name = str(item.Class.Name)
        if "Weapon" in cls_name:
            return read_weapon_stats(item)
        else:
            return read_item_stats(item)
    except Exception:
        return read_item_stats(item)


# =============================================================================
# STATUS MENU (Tab menu - inventory/skills/missions/map)
# =============================================================================

def _on_status_menu_start(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when the status menu (Tab) opens."""
    tts.speak("Status menu. Inventory tab.", True)


def _on_status_menu_close(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when the status menu closes."""
    tts.speak("Menu closed.", True)


def _on_status_menu_tab_change(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when switching tabs in status menu."""
    try:
        tab_names = ["Inventory", "Skills", "Badass Rank", "Mission Log"]
        idx = int(args.TabIdx) if hasattr(args, 'TabIdx') else -1
        if 0 <= idx < len(tab_names):
            tts.speak(tab_names[idx] + " tab.", True)
    except Exception:
        pass


# =============================================================================
# INVENTORY NAVIGATION
# =============================================================================

def _on_inventory_focus(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when an inventory item is focused/highlighted."""
    global _last_item_spoken
    try:
        item = None
        # Try different ways to get the focused item
        for attr in ('FocusedItem', 'SelectedItem', 'HighlightedItem'):
            try:
                item = getattr(obj, attr, None)
                if item is not None:
                    break
            except Exception:
                continue

        if item is not None:
            text = read_inventory_item(item)
            if text != _last_item_spoken:
                _last_item_spoken = text
                tts.speak(text, True)
    except Exception:
        pass


# =============================================================================
# ITEM PICKUP / DROP
# =============================================================================

def _on_item_pickup(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player picks up an item."""
    try:
        item = args.Inventory if hasattr(args, 'Inventory') else None
        if item is None:
            item = args.Item if hasattr(args, 'Item') else None
        if item is not None:
            text = read_inventory_item(item)
            tts.speak("Picked up " + text, True)
    except Exception:
        pass


def _on_weapon_equip(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a weapon is equipped."""
    try:
        weapon = args.NewWeapon if hasattr(args, 'NewWeapon') else None
        if weapon is None:
            weapon = args.Weapon if hasattr(args, 'Weapon') else None
        if weapon is not None:
            text = read_weapon_stats(weapon)
            tts.speak("Equipped " + text, True)
    except Exception:
        pass


def _on_weapon_switch(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player switches weapons (scroll wheel or number keys)."""
    try:
        # Get current active weapon
        pc = obj
        if hasattr(pc, 'Pawn') and pc.Pawn is not None:
            weapon = pc.Pawn.Weapon
            if weapon is not None:
                text = read_weapon_stats(weapon)
                tts.speak(text, True)
    except Exception:
        pass


# =============================================================================
# ITEM CARD (tooltip / inspect)
# =============================================================================

def _on_item_card_show(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when an item card/tooltip appears."""
    global _last_item_spoken
    try:
        item = args.InventoryItem if hasattr(args, 'InventoryItem') else None
        if item is None:
            item = args.Item if hasattr(args, 'Item') else None
        if item is not None:
            text = read_inventory_item(item)
            if text != _last_item_spoken:
                _last_item_spoken = text
                tts.speak(text, True)
    except Exception:
        pass


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all inventory reader hooks."""
    # Status menu lifecycle
    hooks.add_hook(
        "WillowGame.StatusMenuGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_status_start", _on_status_menu_start
    )

    # Weapon switching
    hooks.add_hook(
        "WillowGame.WillowPlayerController:SwitchToWeapon",
        hooks.Type.POST, "bl2a11y_weapon_switch", _on_weapon_switch
    )

    # Item pickup
    hooks.add_hook(
        "WillowGame.WillowInventoryManager:AddInventory",
        hooks.Type.POST, "bl2a11y_item_pickup", _on_item_pickup
    )


def unregister_hooks():
    """Remove all inventory reader hooks."""
    hooks.remove_hook("WillowGame.StatusMenuGFxMovie:Start", hooks.Type.POST, "bl2a11y_status_start")
    hooks.remove_hook("WillowGame.WillowPlayerController:SwitchToWeapon", hooks.Type.POST, "bl2a11y_weapon_switch")
    hooks.remove_hook("WillowGame.WillowInventoryManager:AddInventory", hooks.Type.POST, "bl2a11y_item_pickup")
