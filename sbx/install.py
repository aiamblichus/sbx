"""Installation helper to set up default profiles."""

import shutil
from pathlib import Path

from importlib import resources


def install_default_profiles() -> None:
    """Copy default profiles to user config directory."""
    config_dir = Path.home() / ".local" / "share" / "sbx"
    profiles_dir = config_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    # Try to copy package profiles
    try:
        package = resources.files("sbx.profiles")
        if package.is_dir():
            for profile_file in package.iterdir():
                if profile_file.name.endswith(".toml") and profile_file.is_file():
                    dest_file = profiles_dir / profile_file.name
                    if not dest_file.exists():
                        with resources.as_file(profile_file) as src_path:
                            shutil.copy2(src_path, dest_file)
    except (ModuleNotFoundError, AttributeError):
        # Fallback: try relative path from this file
        package_profiles = Path(__file__).parent / "profiles"
        if package_profiles.exists():
            for profile_file in package_profiles.glob("*.toml"):
                dest_file = profiles_dir / profile_file.name
                if not dest_file.exists():
                    shutil.copy2(profile_file, dest_file)

    # Copy executables.toml if it doesn't exist
    config_dir.mkdir(parents=True, exist_ok=True)
    dest_executables = config_dir / "executables.toml"
    if not dest_executables.exists():
        try:
            exec_file = resources.files("sbx.profiles") / "executables.toml"
            if exec_file.exists():
                with resources.as_file(exec_file) as src_path:
                    shutil.copy2(src_path, dest_executables)
        except (ModuleNotFoundError, AttributeError):
            # Fallback
            package_executables = (
                Path(__file__).parent / "profiles" / "executables.toml"
            )
            if package_executables.exists():
                shutil.copy2(package_executables, dest_executables)
