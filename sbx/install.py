"""Installation helper to set up default profiles."""

import shutil
from pathlib import Path

from importlib import resources
from rich import print


def install_default_profiles(force: bool = False) -> None:
    """Copy default profiles to user config directory."""
    config_dir = Path.home() / ".local" / "config" / "sbx"
    profiles_dir = config_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    # Try to copy package profiles
    try:
        package = resources.files("sbx.profiles")
        if package.is_dir():
            for profile_file in package.iterdir():
                if profile_file.name.endswith(".yaml") and profile_file.is_file():
                    dest_file = profiles_dir / profile_file.name
                    if not dest_file.exists() or force:
                        print(
                            f"[green]Copying profile file {profile_file} to {dest_file}[/green]"
                        )
                        with resources.as_file(profile_file) as src_path:
                            _ = shutil.copy2(src_path, dest_file)
    except (ModuleNotFoundError, AttributeError):
        # Fallback: try relative path from this file
        package_profiles = Path(__file__).parent / "profiles"
        if package_profiles.exists():
            for profile_file in package_profiles.glob("*.yaml"):
                dest_file = profiles_dir / profile_file.name
                if not dest_file.exists():
                    _ = shutil.copy2(profile_file, dest_file)
