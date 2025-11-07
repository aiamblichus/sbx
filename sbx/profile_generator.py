"""Generates macOS sandbox-exec Scheme profiles from TOML definitions."""

from pathlib import Path
from typing import Any

import tomllib

from sbx.models import FilesystemConfig, ProfileConfig, ProfileOverrides


class ProfileGenerator:
    """Generates Scheme sandbox profiles from TOML configuration."""

    def __init__(self, profiles_dir: Path, cache_dir: Path | None = None):
        self.profiles_dir: Path = profiles_dir
        self.cache_dir: Path | None = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def load_profile(self, name: str) -> ProfileConfig:
        """Load a TOML profile."""
        # Try user config directory first
        profile_path = self.profiles_dir / f"{name}.toml"
        if not profile_path.exists():
            # Fall back to package profiles
            package_profiles = Path(__file__).parent / "profiles" / f"{name}.toml"
            if package_profiles.exists():
                profile_path = package_profiles
            else:
                raise FileNotFoundError(
                    f"Profile '{name}' not found at {profile_path} or {package_profiles}"
                )

        with open(profile_path, "rb") as f:
            data = tomllib.load(f)
            return ProfileConfig.from_dict(data)

    def merge_profiles(
        self, profile_names: list[str], overrides: ProfileOverrides | None = None
    ) -> ProfileConfig:
        """Merge multiple profiles with optional overrides."""
        merged_dict: dict[str, Any] = {}

        for name in profile_names:
            profile = self.load_profile(name)
            profile_dict = profile.to_dict()
            merged_dict = self._deep_merge(merged_dict, profile_dict)

        if overrides:
            merged_dict = self._deep_merge(merged_dict, overrides)

        return ProfileConfig.from_dict(merged_dict)

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
        lines.append("  (subpath (string-append home-path home-relative-subpath)))")
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
        path = self._substitute_vars(path, params)

        # Handle absolute paths
        if path.startswith("/"):
            return f'(subpath "{path}")'
        # Handle regex patterns
        elif path.startswith("^") or "*" in path or "?" in path:
            return f'(regex #"{path}")'
        # Handle home-relative paths
        elif path.startswith("~/"):
            return f'(home-subpath "{path[2:]}")'
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

    def _deep_merge(
        self, base: dict[str, Any], override: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep merge two dictionaries."""
        result: dict[str, Any] = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            elif (
                isinstance(value, list)
                and key in result
                and isinstance(result[key], list)
            ):
                # Merge lists (append new items)
                result[key] = result[key] + value
            else:
                result[key] = value
        return result
