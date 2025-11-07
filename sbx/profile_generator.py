"""Generates macOS sandbox-exec Scheme profiles from YAML definitions."""

from pathlib import Path
from typing import Any

import yaml

from sbx.models import FilesystemConfig, ProfileConfig, ProfileOverrides


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Merging rules:
    - If both values are dicts, recursively merge them
    - If both values are lists, concatenate them (base + override)
    - If key exists in base but types don't match, override replaces base
    - If key doesn't exist in base, add it from override
    """
    result: dict[str, Any] = base.copy()
    for key, value in override.items():
        if key in result:
            # Key exists in base
            if isinstance(result[key], dict) and isinstance(value, dict):
                # Both are dicts - recursively merge
                result[key] = deep_merge(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                # Both are lists - concatenate (preserve order: base first, then override)
                result[key] = result[key] + value
            else:
                # Types don't match or one is not dict/list - override replaces base
                result[key] = value
        else:
            # Key doesn't exist in base - add it from override
            result[key] = value
    return result


class ProfileGenerator:
    """Generates Scheme sandbox profiles from YAML configuration."""

    def __init__(self, profiles_dir: Path, cache_dir: Path | None = None):
        self.profiles_dir: Path = profiles_dir
        self.cache_dir: Path | None = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def load_profile(self, name: str) -> ProfileConfig:
        """Load a YAML profile."""
        # Try user config directory first
        profile_path = self.profiles_dir / f"{name}.yaml"
        if not profile_path.exists():
            # Fall back to package profiles
            package_profiles = Path(__file__).parent / "profiles" / f"{name}.yaml"
            if package_profiles.exists():
                profile_path = package_profiles
            else:
                raise FileNotFoundError(
                    f"Profile '{name}' not found at {profile_path} or {package_profiles}"
                )

        with open(profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data is None:
                raise ValueError(f"Profile '{name}' is empty or invalid")
            return ProfileConfig.from_dict(data)

    def merge_profiles(
        self, profile_names: list[str], overrides: ProfileOverrides | None = None
    ) -> ProfileConfig:
        """Merge multiple profiles with optional overrides."""
        merged_dict: dict[str, Any] = {}

        for name in profile_names:
            profile = self.load_profile(name)
            profile_dict = profile.to_dict()
            merged_dict = deep_merge(merged_dict, profile_dict)

        if overrides:
            merged_dict = deep_merge(merged_dict, overrides)

        # Normalize the merged dict to ensure consistent structure
        # This handles cases where overrides might create flat keys like "filesystem.read.paths"
        # instead of nested "filesystem.read.paths"
        merged_dict = self._normalize_dict_structure(merged_dict)

        # Convert merged dict back to ProfileConfig
        # This will validate and normalize the structure
        return ProfileConfig.from_dict(merged_dict)

    def _normalize_dict_structure(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize dictionary structure to handle flat keys like 'filesystem.read.paths'.

        Converts flat keys like {'filesystem.read.paths': [...]} into nested structure
        {'filesystem': {'read': {'paths': [...]}}}
        """
        result: dict[str, Any] = {}

        for key, value in data.items():
            if "." in key:
                # This is a flat key that should be nested
                keys = key.split(".")
                current = result
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    elif not isinstance(current[k], dict):
                        # Conflict: key exists but isn't a dict
                        # Merge the existing value into the nested structure
                        existing_value = current[k]
                        current[k] = {}
                        # Try to preserve existing structure if it's a dict
                        if isinstance(existing_value, dict):
                            current[k].update(existing_value)
                    current = current[k]

                final_key = keys[-1]
                # If the final key already exists, merge lists if both are lists
                if final_key in current:
                    if isinstance(current[final_key], list) and isinstance(value, list):
                        current[final_key] = current[final_key] + value
                    elif isinstance(current[final_key], dict) and isinstance(
                        value, dict
                    ):
                        current[final_key] = deep_merge(current[final_key], value)
                    else:
                        current[final_key] = value
                else:
                    current[final_key] = value
            else:
                # Regular nested key
                if key in result:
                    if isinstance(result[key], dict) and isinstance(value, dict):
                        result[key] = deep_merge(result[key], value)
                    elif isinstance(result[key], list) and isinstance(value, list):
                        result[key] = result[key] + value
                    else:
                        result[key] = value
                else:
                    result[key] = value

        return result

    def generate_scheme(self, config: ProfileConfig, params: dict[str, str]) -> str:
        """Generate Scheme sandbox profile from merged config."""
        lines: list[str] = ["(version 1)"]

        # Handle imports first (before deny default)
        if config.imports:
            for imp in config.imports.system_profiles:
                lines.append(f'(import "{imp}")')

        # Default deny
        if config.filesystem and config.filesystem.default_deny:
            lines.append("(deny default)")

        # Helper function definitions
        lines.append("")
        lines.append('(define home-path (param "home"))')
        lines.append("")
        lines.append("(define (home-subpath home-relative-subpath)")
        lines.append('  (subpath (string-append home-path "/" home-relative-subpath)))')
        lines.append("")

        # Network rules
        if config.network:
            if config.network.enabled:
                lines.append("(allow network*)")
            elif config.network.allow_localhost:
                lines.append('(allow network* (to ip "localhost:*"))')
                lines.append('(allow network-inbound (from ip "localhost:*"))')

        # File system rules
        if config.filesystem:
            self._add_file_rules(lines, config.filesystem, params)

        # Process rules
        if config.process:
            if config.process.allow_exec:
                lines.append("(allow process-exec)")
            if config.process.allow_fork:
                lines.append("(allow process-fork)")

        # System rules
        if config.system:
            if config.system.allow_user_preferences:
                lines.append("(allow user-preference-read)")
            if config.system.allow_sysctl_write:
                lines.append("(allow sysctl-write)")
            if config.system.allow_system_debug:
                lines.append("(allow system-debug)")
            if config.system.allow_mach_priv_task_port:
                lines.append("(allow mach-priv-task-port)")

        # Mach rules
        if config.mach:
            for name in config.mach.lookup:
                lines.append(f'(allow mach-lookup (global-name "{name}"))')

            for regex in config.mach.lookup_regex:
                lines.append(f'(allow mach-lookup (global-name-regex "{regex}"))')

        # IPC rules
        if config.ipc:
            if config.ipc.allow_posix_shm:
                if config.ipc.posix_shm_names:
                    lines.append("(allow ipc-posix-shm")
                    for name in config.ipc.posix_shm_names:
                        lines.append(f'       (ipc-posix-name "{name}")')
                    lines.append(")")
                else:
                    lines.append("(allow ipc-posix-shm)")

            if config.ipc.allow_posix_sem:
                lines.append("(allow ipc-posix-sem)")

        # Signal rules
        if config.signal and config.signal.target:
            lines.append(f"(allow signal (target {config.signal.target}))")

        # IOKit rules
        if config.iokit:
            for name in config.iokit.open:
                lines.append(f'(allow iokit-open (global-name "{name}"))')

        return "\n".join(lines)

    def _add_file_rules(
        self, lines: list[str], fs: FilesystemConfig, params: dict[str, str]
    ) -> None:
        """Add file system allow rules."""

        # Read-only paths
        read_config = fs.read
        if read_config:
            read_paths = read_config.paths
            read_regexes = read_config.regex

            if read_paths or read_regexes:
                lines.append("(allow file-read*")
                for path in read_paths:
                    formatted = self._format_path(path, params)
                    lines.append(f"       {formatted}")
                for regex in read_regexes:
                    formatted_regex = self._substitute_vars(regex, params)
                    lines.append(f'       (regex #"{formatted_regex}")')
                lines.append(")")

        # Write paths
        write_config = fs.write
        if write_config:
            write_paths = write_config.paths
            write_regexes = write_config.regex

            if write_paths or write_regexes:
                lines.append("(allow file*")
                for path in write_paths:
                    formatted = self._format_path(path, params)
                    lines.append(f"       {formatted}")
                for regex in write_regexes:
                    formatted_regex = self._substitute_vars(regex, params)
                    lines.append(f'       (regex #"{formatted_regex}")')
                lines.append(")")

    def _format_path(self, path: str, params: dict[str, str]) -> str:
        """Format path with variable substitution."""
        # Check for home-relative paths BEFORE substitution
        if path.startswith("~/"):
            # Use home-subpath helper function for home-relative paths
            relative_path = path[2:]  # Remove "~/"
            # Still substitute other vars like {working-directory}
            relative_path = self._substitute_vars(relative_path, params)
            return f'(home-subpath "{relative_path}")'

        # Substitute variables for other path types
        path = self._substitute_vars(path, params)

        # Handle absolute paths
        if path.startswith("/"):
            return f'(subpath "{path}")'
        # Handle regex patterns
        elif path.startswith("^") or "*" in path or "?" in path:
            return f'(regex #"{path}")'
        # Handle literal paths
        else:
            return f'(literal "{path}")'

    def _substitute_vars(self, text: str, params: dict[str, str]) -> str:
        """Substitute variables in text."""
        result = text
        result = result.replace("~", params.get("home", ""))
        result = result.replace(
            "{working-directory}", params.get("working-directory", "")
        )
        result = result.replace("{home}", params.get("home", ""))
        return result
