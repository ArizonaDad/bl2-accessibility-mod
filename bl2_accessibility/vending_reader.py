"""
Vending Machine Reader - Reads vending machine items, costs, and comparisons via TTS.
Covers: Ammo dump, gun vendor, medical vendor, black market.
"""

import unrealsdk
from unrealsdk import hooks
from unrealsdk.unreal import UObject, WrappedStruct, BoundFunction

from . import tts
from .inventory_reader import read_inventory_item, get_rarity_name


def _on_vending_open(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when a vending machine menu opens."""
    try:
        vendor_type = "Vending machine"
        try:
            name = str(obj.VendorName) if hasattr(obj, 'VendorName') else ""
            if not name:
                name = str(obj.Name) if hasattr(obj, 'Name') else ""
            if name:
                lower = name.lower()
                if "ammo" in lower:
                    vendor_type = "Ammo vendor"
                elif "medical" in lower or "health" in lower:
                    vendor_type = "Medical vendor"
                elif "weapon" in lower or "gun" in lower:
                    vendor_type = "Gun vendor"
                elif "black" in lower or "market" in lower:
                    vendor_type = "Black market"
                elif "seraph" in lower:
                    vendor_type = "Seraph vendor"
                else:
                    vendor_type = name
        except Exception:
            pass

        # Read player's money
        money_text = ""
        try:
            pc = None
            for p in unrealsdk.find_all("WillowPlayerController", exact=False):
                pc = p
                break
            if pc is not None:
                pri = pc.PlayerReplicationInfo
                money = int(pri.PlayerMoney) if hasattr(pri, 'PlayerMoney') else 0
                money_text = f" You have ${money}."
        except Exception:
            pass

        tts.speak(f"{vendor_type} opened.{money_text} Navigate items with up and down.", True)
    except Exception:
        tts.speak("Vending machine opened.", True)


def _on_vending_close(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when vending machine closes."""
    tts.speak("Vendor closed.", True)


def _on_vending_item_focus(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when an item in the vending machine is focused."""
    try:
        item = None
        cost = 0

        # Try to get focused item
        for attr in ('FocusedItem', 'SelectedItem', 'HighlightedItem'):
            try:
                item = getattr(obj, attr, None)
                if item is not None:
                    break
            except Exception:
                continue

        # Try to get cost
        try:
            cost = int(args.Cost) if hasattr(args, 'Cost') else 0
            if cost == 0:
                cost = int(args.Price) if hasattr(args, 'Price') else 0
        except Exception:
            pass

        if item is not None:
            text = read_inventory_item(item)
            if cost > 0:
                text += f", costs ${cost}"
            tts.speak(text, True)
    except Exception:
        pass


def _on_vending_purchase(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player buys from vendor."""
    try:
        item = args.InventoryItem if hasattr(args, 'InventoryItem') else None
        if item is None:
            item = args.Item if hasattr(args, 'Item') else None
        if item is not None:
            text = read_inventory_item(item)
            tts.speak(f"Purchased {text}.", True)
        else:
            tts.speak("Item purchased.", True)
    except Exception:
        tts.speak("Purchase complete.", True)


def _on_vending_sell(obj: UObject, args: WrappedStruct, ret, func: BoundFunction):
    """Called when player sells to vendor."""
    try:
        item = args.InventoryItem if hasattr(args, 'InventoryItem') else None
        if item is None:
            item = args.Item if hasattr(args, 'Item') else None
        if item is not None:
            text = read_inventory_item(item)
            tts.speak(f"Sold {text}.", True)
        else:
            tts.speak("Item sold.", True)
    except Exception:
        tts.speak("Item sold.", True)


# =============================================================================
# HOOK REGISTRATION
# =============================================================================

def register_hooks():
    """Register all vending machine hooks."""
    hooks.add_hook(
        "WillowGame.VendingMachineGFxMovie:Start",
        hooks.Type.POST, "bl2a11y_vending_start", _on_vending_open
    )


def unregister_hooks():
    """Remove all vending machine hooks."""
    hooks.remove_hook("WillowGame.VendingMachineGFxMovie:Start", hooks.Type.POST, "bl2a11y_vending_start")
