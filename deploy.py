"""
Deploy script: creates a symlink from the BL2 sdk_mods folder to this project's mod folder.
Run once to set up, then edits to the project files are live in-game.
"""

import os
import sys

BL2_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2"
SDK_MODS_PATH = os.path.join(BL2_PATH, "sdk_mods")
MOD_NAME = "bl2_accessibility"
SOURCE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), MOD_NAME)
LINK_PATH = os.path.join(SDK_MODS_PATH, MOD_NAME)


def main():
    if not os.path.isdir(SDK_MODS_PATH):
        print(f"ERROR: SDK mods directory not found at {SDK_MODS_PATH}")
        print("Make sure PythonSDK is installed.")
        sys.exit(1)

    if not os.path.isdir(SOURCE_PATH):
        print(f"ERROR: Mod source not found at {SOURCE_PATH}")
        sys.exit(1)

    if os.path.exists(LINK_PATH):
        if os.path.islink(LINK_PATH):
            print(f"Symlink already exists: {LINK_PATH} -> {os.readlink(LINK_PATH)}")
            print("Removing old symlink...")
            os.remove(LINK_PATH)
        elif os.path.isdir(LINK_PATH):
            print(f"WARNING: {LINK_PATH} is a regular directory, not a symlink.")
            print("Please remove it manually if you want to use symlink deployment.")
            sys.exit(1)

    try:
        os.symlink(SOURCE_PATH, LINK_PATH, target_is_directory=True)
        print(f"Symlink created: {LINK_PATH} -> {SOURCE_PATH}")
        print("Mod is now live! Changes to the project folder will be reflected in-game.")
        print("Restart BL2 for the mod to load.")
    except OSError as e:
        if "privilege" in str(e).lower() or "1314" in str(e):
            print("Symlink failed (requires admin or Developer Mode).")
            print("Falling back to directory junction...")
            import subprocess
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", LINK_PATH, SOURCE_PATH],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"Junction created: {LINK_PATH} -> {SOURCE_PATH}")
                print("Mod is now live!")
            else:
                print(f"Junction also failed: {result.stderr}")
                print("Try running this script as administrator.")
                sys.exit(1)
        else:
            print(f"Error creating symlink: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
