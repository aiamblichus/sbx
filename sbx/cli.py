"""Main CLI for sbx."""

import os
import sys
import tempfile
import fnmatch
import shutil
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python

from sbx.profile_generator import ProfileGenerator
from sbx.install import install_default_profiles


def get_config_dir() -> Path:
    """Get the sbx configuration directory."""
    config_dir = Path.home() / ".local" / "share" / "sbx"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_profiles_dir() -> Path:
    """Get the profiles directory."""
    profiles_dir = get_config_dir() / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


def find_executable_config(cmd: str) -> dict[str, Any]:
    """Find matching executable config from executables.toml."""
    config_file = get_config_dir() / "executables.toml"
    if not config_file.exists():
        return {}

    try:
        with open(config_file, "rb") as f:
            config = tomllib.load(f)
    except Exception:
        return {}

    for exec_config in config.get("executables", []):
        pattern = exec_config.get("pattern", "")
        if not pattern:
            continue

        # Try matching the command name
        if fnmatch.fnmatch(cmd, pattern):
            return exec_config

        # Try matching with full path
        if fnmatch.fnmatch(f"/{cmd}", pattern):
            return exec_config

        # Try matching just the basename
        cmd_basename = os.path.basename(cmd)
        if fnmatch.fnmatch(cmd_basename, pattern):
            return exec_config

    return {}


def parse_overrides(args: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Parse inline override arguments like +network.enabled=true."""
    profiles = []
    overrides: dict[str, Any] = {}

    for arg in args:
        if arg.startswith("+") or arg.startswith("override:"):
            # Parse override: network.enabled=true or +network.enabled=true
            override_str = arg.lstrip("+override:")
            if "=" in override_str:
                path, value = override_str.split("=", 1)
                # Convert value to appropriate type
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                else:
                    try:
                        value = float(value)
                    except ValueError:
                        pass  # Keep as string

                # Set nested dict value
                keys = path.split(".")
                current = overrides
                for key in keys[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[keys[-1]] = value
        else:
            profiles.append(arg)

    return profiles, overrides


def main() -> None:
    """Main entry point."""
    # Handle version flag
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        from sbx import __version__

        print(f"sbx {__version__}")
        sys.exit(0)

    # Ensure default profiles are installed
    install_default_profiles()

    profiles: list[str] = ["base"]
    overrides: dict[str, Any] = {}
    command: list[str] | None = None

    # Parse arguments
    args = sys.argv[1:]
    if "--" in args:
        idx = args.index("--")
        command = args[idx + 1 :]
        args = args[:idx]

    # Parse profile arguments and overrides
    parsed_profiles, parsed_overrides = parse_overrides(args)
    if parsed_profiles:
        # If user specified profiles, use them (but still include base if not explicitly excluded)
        profiles = parsed_profiles
        # Ensure base is included unless explicitly excluded
        if "base" not in profiles and "no-base" not in profiles:
            profiles = ["base"] + profiles
    if parsed_overrides:
        overrides = parsed_overrides

    # If command provided, check for executable-specific config
    if command:
        exec_config = find_executable_config(command[0])
        if exec_config:
            exec_profiles = exec_config.get("profiles")
            if exec_profiles:
                profiles = exec_profiles
            exec_overrides = exec_config.get("overrides", {})
            # Merge executable overrides with command-line overrides (CLI takes precedence)
            overrides = {**exec_overrides, **overrides}

    # Generate profile
    profiles_dir = get_profiles_dir()
    generator = ProfileGenerator(profiles_dir)

    try:
        merged_config = generator.merge_profiles(profiles, overrides)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    params = {
        "home": str(Path.home()),
        "working-directory": str(Path.cwd()),
        "sbx": str(get_config_dir()),
    }

    scheme_profile = generator.generate_scheme(merged_config, params)

    # Write temporary profile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False) as f:
        f.write(scheme_profile)
        profile_path = f.name

    # Set environment variables
    env = os.environ.copy()
    network_enabled = merged_config.get("network", {}).get("enabled", False)
    env["SANDBOX_MODE_NETWORK"] = "online" if network_enabled else "offline"

    # Prepare command
    if command:
        # Resolve the executable path
        executable = command[0]
        resolved_path = shutil.which(executable)
        if not resolved_path:
            print(
                f"Error: Could not find executable '{executable}' in PATH",
                file=sys.stderr,
            )
            sys.exit(1)
        # Replace the command with the resolved path
        resolved_command = [resolved_path] + command[1:]
        # Execute through /bin/sh to ensure compatibility with sandbox profiles
        # /bin/sh is more likely to be allowed than custom shells like zsh
        shell = "/bin/sh"
        # Build shell command: shell -c "executable args..."
        # Properly escape arguments for shell
        shell_args = shlex.join(resolved_command)
        shell_cmd = [shell, "-c", shell_args]
        cmd = ["sandbox-exec", "-f", profile_path] + shell_cmd
    else:
        # Use /bin/sh as default for interactive shell too
        shell = os.environ.get("SHELL", "/bin/sh")
        if not os.path.exists(shell):
            shell = "/bin/sh"
        cmd = ["sandbox-exec", "-f", profile_path, shell]

    # Execute sandbox
    # Use subprocess to execute sandbox-exec
    # Use full path to sandbox-exec for reliability
    sandbox_exec_path = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
    cmd[0] = sandbox_exec_path
    sys.exit(subprocess.call(cmd, env=env))


if __name__ == "__main__":
    main()
