"""Configuration loader for executable-specific profiles."""

from pathlib import Path
from typing import Any

import yaml

from sbx.models import ExecutablesConfig, ProfileOverrides


def parse_dot_notation_overrides(data: dict[str, Any]) -> ProfileOverrides:
    """Parse dot-notation keys (like 'network.enabled') into nested dictionaries."""
    result: ProfileOverrides = {}  # type: ignore[type-arg]
    for key, value in data.items():
        keys = key.split(".")
        current = result
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
    return result


def load_executable_config(config_path: Path | None = None) -> ExecutablesConfig | None:
    """Load executable configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        ExecutablesConfig if file exists and is valid, None otherwise.
    """
    if config_path is None:
        config_path = Path.home() / ".local" / "config" / "sbx" / "config.yaml"

    if not config_path.exists():
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data is None:
                return None

            # Handle dot-notation overrides in executable configs
            if "executables" in data:
                for _, exec_config in data["executables"].items():
                    if isinstance(exec_config, dict) and "overrides" in exec_config:
                        if isinstance(exec_config["overrides"], dict):
                            exec_config["overrides"] = parse_dot_notation_overrides(
                                exec_config["overrides"]
                            )

            return ExecutablesConfig.from_dict(data)
    except (yaml.YAMLError, ValueError) as e:
        # Log error but don't fail - config is optional
        import sys

        print(
            f"Warning: Failed to load config file {config_path}: {e}",
            file=sys.stderr,
        )
        return None


def find_matching_executable_configs(
    executable_name: str, config: ExecutablesConfig
) -> list[tuple[list[str], ProfileOverrides]]:
    """Find all executable configs that match the given executable name.

    Args:
        executable_name: Name of the executable (without path).
        config: ExecutablesConfig to search.

    Returns:
        List of tuples (profiles_list, overrides_dict) for matching configs.
        Results are ordered by appearance in config file.
    """
    matches: list[tuple[list[str], ProfileOverrides]] = []
    for exec_config in config.executables.values():
        if exec_config.matches(executable_name):
            matches.append((exec_config.profiles, exec_config.overrides))
    return matches
