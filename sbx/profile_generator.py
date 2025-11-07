"""Generates macOS sandbox-exec Scheme profiles from TOML definitions."""

from pathlib import Path
from typing import Any

import tomllib


class ProfileGenerator:
    """Generates Scheme sandbox profiles from TOML configuration."""

    def __init__(self, profiles_dir: Path, cache_dir: Path | None = None):
        self.profiles_dir = profiles_dir
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def load_profile(self, name: str) -> dict[str, Any]:
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
            return tomllib.load(f)

    def merge_profiles(
        self, profile_names: list[str], overrides: dict | None = None
    ) -> dict:
        """Merge multiple profiles with optional overrides."""
        merged: dict[str, Any] = {}

        for name in profile_names:
            profile = self.load_profile(name)
            merged = self._deep_merge(merged, profile)

        if overrides:
            merged = self._deep_merge(merged, overrides)

        return merged

    def generate_scheme(self, config: dict[str, Any], params: dict[str, str]) -> str:
        """Generate Scheme sandbox profile from merged config."""
        lines: list[str] = ["(version 1)"]

        # Handle imports first (before deny default)
        imports = config.get("imports", {})
        for imp in imports.get("system_profiles", []):
            lines.append(f'(import "{imp}")')

        # Default deny
        if config.get("filesystem", {}).get("default_deny", False):
            lines.append("(deny default)")

        # Helper function definitions
        lines.append("")
        lines.append('(define home-path (param "home"))')
        lines.append("")
        lines.append("(define (home-subpath home-relative-subpath)")
        lines.append("  (subpath (string-append home-path home-relative-subpath)))")
        lines.append("")

        # Network rules
        network = config.get("network", {})
        if network.get("enabled", False):
            lines.append("(allow network*)")
        elif network.get("allow_localhost", False):
            lines.append('(allow network* (to ip "localhost:*"))')
            lines.append('(allow network-inbound (from ip "localhost:*"))')

        # File system rules
        fs = config.get("filesystem", {})
        self._add_file_rules(lines, fs, params)

        # Process rules
        process = config.get("process", {})
        if process.get("allow_exec", False):
            lines.append("(allow process-exec)")
        if process.get("allow_fork", False):
            lines.append("(allow process-fork)")

        # System rules
        system = config.get("system", {})
        if system.get("allow_user_preferences", False):
            lines.append("(allow user-preference-read)")
        if system.get("allow_sysctl_write", False):
            lines.append("(allow sysctl-write)")
        if system.get("allow_system_debug", False):
            lines.append("(allow system-debug)")
        if system.get("allow_mach_priv_task_port", False):
            lines.append("(allow mach-priv-task-port)")

        # Mach rules
        mach = config.get("mach", {})
        lookup_names = mach.get("lookup", [])
        for name in lookup_names:
            lines.append(f'(allow mach-lookup (global-name "{name}"))')

        lookup_regexes = mach.get("lookup_regex", [])
        for regex in lookup_regexes:
            lines.append(f'(allow mach-lookup (global-name-regex "{regex}"))')

        # IPC rules
        ipc = config.get("ipc", {})
        if ipc.get("allow_posix_shm", False):
            shm_names = ipc.get("posix_shm_names", [])
            if shm_names:
                lines.append("(allow ipc-posix-shm")
                for name in shm_names:
                    lines.append(f'       (ipc-posix-name "{name}")')
                lines.append(")")
            else:
                lines.append("(allow ipc-posix-shm)")

        if ipc.get("allow_posix_sem", False):
            lines.append("(allow ipc-posix-sem)")

        # Signal rules
        signal = config.get("signal", {})
        if signal.get("target"):
            target = signal["target"]
            lines.append(f"(allow signal (target {target}))")

        # IOKit rules
        iokit = config.get("iokit", {})
        for name in iokit.get("open", []):
            lines.append(f'(allow iokit-open (global-name "{name}"))')

        return "\n".join(lines)

    def _add_file_rules(
        self, lines: list[str], fs: dict[str, Any], params: dict[str, str]
    ) -> None:
        """Add file system allow rules."""
        # Read-only paths
        read_config = fs.get("read", {})
        read_paths = read_config.get("paths", [])
        read_regexes = read_config.get("regex", [])
        if not isinstance(read_regexes, list):
            read_regexes = []

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
        write_config = fs.get("write", {})
        write_paths = write_config.get("paths", [])
        write_regexes = write_config.get("regex", [])
        if not isinstance(write_regexes, list):
            write_regexes = []

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
        result = base.copy()
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
