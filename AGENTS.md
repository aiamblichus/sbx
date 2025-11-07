# sbx Project Briefing

## Overview

**sbx** is a Python-based wrapper around macOS's `sandbox-exec` utility that provides a user-friendly way to run terminals and programs within sandboxes. It translates TOML-based profile configurations into Scheme sandbox profiles that macOS can execute, making it easier to restrict filesystem and network access for untrusted code.

### Purpose

The tool addresses the security concern that package managers (npm, cargo, pip, etc.) and their transitive dependencies have full access to your filesystem and network. By running these tools in sandboxes, you can limit what they can access while still allowing them to function.

### Key Value Propositions

- **TOML-based profiles**: Human-readable configuration instead of Scheme syntax
- **Profile composition**: Combine multiple profiles with intelligent merging
- **Command-line flexibility**: Override profile settings on the fly
- **User customization**: Profiles stored in `~/.local/config/sbx/` for easy modification

## Architecture

### High-Level Flow

```
User Command → CLI Parser → Profile Loader → Profile Merger → Scheme Generator → sandbox-exec → Sandboxed Process
```

1. **CLI Parsing** (`cli.py`): Parses command-line arguments, extracts profile names and overrides
2. **Profile Loading** (`profile_generator.py`): Loads TOML profiles from user config or package defaults
3. **Profile Merging** (`profile_generator.py`): Combines multiple profiles with deep merging
4. **Scheme Generation** (`profile_generator.py`): Converts merged TOML config to Scheme syntax
5. **Execution** (`cli.py`): Writes temporary Scheme file and executes via `sandbox-exec`

### Core Components

#### 1. CLI Module (`sbx/cli.py`)

**Responsibilities:**

- Parse command-line arguments
- Handle version flags and profile installation
- Extract profile names and command-line overrides
- Resolve executable paths
- Execute `sandbox-exec` with generated profile
- Set environment variables (`SANDBOX_MODE_NETWORK`)

**Key Functions:**

- `main()`: Entry point, orchestrates the entire flow
- `parse_overrides()`: Parses `+key=value` syntax into nested dictionaries
- `get_config_dir()`: Returns `~/.local/config/sbx/`
- `get_profiles_dir()`: Returns `~/.local/config/sbx/profiles/`

**Command-Line Syntax:**

```bash
sbx [profile1] [profile2] [+override.key=value] -- [command] [args...]
```

**Examples:**

- `sbx` → Opens shell with `base` profile
- `sbx online` → Opens shell with `base` + `online` profiles
- `sbx +network.enabled=true -- curl https://example.com` → Override network setting
- `sbx base online -- npm install` → Run npm with combined profiles

#### 2. Profile Generator (`sbx/profile_generator.py`)

**Responsibilities:**

- Load TOML profiles from filesystem
- Merge multiple profiles with deep merging logic
- Convert TOML configuration to Scheme sandbox syntax
- Handle path variable substitution (`~`, `{working-directory}`, etc.)

**Key Classes:**

- `ProfileGenerator`: Main class for profile operations

**Key Methods:**

- `load_profile(name)`: Loads a TOML profile, checks user config first, then package defaults
- `merge_profiles(names, overrides)`: Deep merges multiple profiles and applies overrides
- `generate_scheme(config, params)`: Converts `ProfileConfig` to Scheme string
- `_deep_merge()`: Recursively merges dictionaries, handles list concatenation
- `_format_path()`: Formats paths with variable substitution and Scheme syntax
- `_add_file_rules()`: Generates file read/write rules for Scheme

**Profile Resolution Order:**

1. `~/.local/config/sbx/profiles/{name}.toml` (user profiles)
2. `sbx/profiles/{name}.toml` (package profiles)

#### 3. Data Models (`sbx/models.py`)

**Responsibilities:**

- Define Pydantic models for type-safe configuration
- Validate TOML structure
- Provide serialization/deserialization

**Key Models:**

- `ProfileConfig`: Root configuration model containing all sections
- `NetworkConfig`: Network access settings (`enabled`, `allow_localhost`)
- `FilesystemConfig`: Filesystem permissions with read/write sub-configs
- `FilesystemReadConfig`: Read-only paths and regex patterns
- `FilesystemWriteConfig`: Write paths and regex patterns
- `ProcessConfig`: Process execution and forking permissions
- `SystemConfig`: System-level permissions (user preferences, sysctl, debug, etc.)
- `MachConfig`: Mach port lookup permissions
- `IpcConfig`: IPC permissions (POSIX shared memory, semaphores)
- `SignalConfig`: Signal handling configuration
- `IokitConfig`: IOKit device access
- `ImportsConfig`: System profile imports

**Type Aliases:**

- `ProfileOverrides`: `dict[str, Any]` for command-line override dictionaries

**Model Features:**

- `extra="allow"` on all models to permit additional fields
- `from_dict()`: Class method to create from TOML dictionaries
- `to_dict()`: Excludes `None` and unset values for clean merging

#### 4. Installation Module (`sbx/install.py`)

**Responsibilities:**

- Copy default profiles from package to user config directory
- Handle profile installation on first run or via `--install-profiles` flag

**Key Functions:**

- `install_default_profiles(force=False)`: Copies `.toml` files from `sbx/profiles/` to `~/.local/config/sbx/profiles/`

## Profile System

### Profile Format

Profiles are TOML files with the following structure:

```toml
[profile]
name = "profile-name"
description = "Human-readable description"

[imports]
system_profiles = ["/System/Library/Sandbox/Profiles/bsd.sb"]

[network]
enabled = true
allow_localhost = true

[filesystem]
default_deny = true

[filesystem.read]
paths = ["/bin", "~/.config"]
regex = ["^/Users/.*/Library/.*"]

[filesystem.write]
paths = ["{working-directory}", "~/.cache"]
regex = ["^/dev/tty.*"]

[process]
allow_exec = true
allow_fork = true

[system]
allow_user_preferences = true
allow_sysctl_write = true
allow_system_debug = true
allow_mach_priv_task_port = true

[mach]
lookup = ["com.apple.FSEvents"]
lookup_regex = ["^com.apple.*"]

[ipc]
allow_posix_shm = true
posix_shm_names = ["my-shm"]
allow_posix_sem = true

[signal]
target = "children"

[iokit]
open = ["IOHIDParamUserClient"]
```

### Built-in Profiles

Located in `sbx/profiles/`:

1. **base.toml**: Default offline sandbox

   - Imports `bsd.sb` system profile
   - Network disabled (localhost only)
   - Filesystem: default deny with read access to system binaries and common dev tools
   - Write access to working directory and common cache directories
   - Process execution and forking allowed
   - System permissions for user preferences and debugging

2. **online.toml**: Adds network access

   - Enables full network access
   - Adds Mach port lookups for Apple services

3. **app.toml**: Example GUI application profile (Cyberduck)

   - Network enabled
   - Application directory access
   - IOKit device access

4. **uv_tools.toml**: Profile for `uv` package manager

   - Network enabled
   - Specific paths for uv configuration

5. **gui.toml**: GUI application support

   - Font access
   - Application directory access
   - IOKit access

6. **file-full.toml**: Full filesystem write access
   - Allows writing to `/`

### Profile Merging Logic

Profiles are merged in order using deep merging:

1. **Dictionary merging**: Nested dictionaries are recursively merged
2. **List merging**: Lists are concatenated (new items appended)
3. **Override precedence**: Later profiles override earlier ones
4. **Command-line overrides**: Applied last, highest precedence

**Example:**

```python
# Profile A: {network: {enabled: false}, filesystem: {read: {paths: ["/bin"]}}}
# Profile B: {network: {enabled: true}, filesystem: {read: {paths: ["/usr"]}}}
# Result: {network: {enabled: true}, filesystem: {read: {paths: ["/bin", "/usr"]}}}
```

### Path Variable Substitution

Paths support variable substitution:

- `~` → User home directory (`$HOME`)
- `{home}` → User home directory
- `{working-directory}` → Current working directory
- `{sbx}` → sbx config directory (`~/.local/config/sbx`)

### Scheme Generation

The Scheme output follows this structure:

1. **Version declaration**: `(version 1)`
2. **Imports**: System profile imports (before deny default)
3. **Default deny**: `(deny default)` if `filesystem.default_deny = true`
4. **Helper functions**: `home-path` parameter and `home-subpath` function
5. **Network rules**: `(allow network*)` or localhost-only rules
6. **Filesystem rules**: `(allow file-read*)` and `(allow file*)` with paths/regex
7. **Process rules**: `(allow process-exec)`, `(allow process-fork)`
8. **System rules**: Various system permission allows
9. **Mach rules**: `(allow mach-lookup ...)`
10. **IPC rules**: `(allow ipc-posix-shm ...)`, `(allow ipc-posix-sem)`
11. **Signal rules**: `(allow signal ...)`
12. **IOKit rules**: `(allow iokit-open ...)`

## Configuration System

### User Configuration Directory

All user configuration lives in `~/.local/config/sbx/`:

```
~/.local/config/sbx/
├── profiles/
│   ├── base.toml          # User overrides of base profile
│   ├── online.toml        # User overrides of online profile
│   └── custom.toml        # User-defined profiles
└── executables.toml       # Executable-specific profiles (planned feature)
```

## Execution Flow

### Detailed Step-by-Step

1. **CLI Entry** (`cli.py:main()`)

   - Parse `sys.argv` for version flags, install flags, profiles, overrides, and command
   - Handle `--version` and `--install-profiles` flags early

2. **Profile Resolution**

   - Default to `["base"]` if no profiles specified
   - Always prepend `base` unless `no-base` is explicitly specified
   - Parse `+key=value` overrides into nested dictionary

3. **Profile Loading** (`ProfileGenerator.load_profile()`)

   - Check user profiles directory first
   - Fall back to package profiles
   - Load TOML file and parse into `ProfileConfig` model

4. **Profile Merging** (`ProfileGenerator.merge_profiles()`)

   - Start with empty dictionary
   - Load each profile in order and deep merge
   - Apply command-line overrides last

5. **Scheme Generation** (`ProfileGenerator.generate_scheme()`)

   - Convert merged `ProfileConfig` to Scheme syntax
   - Substitute path variables (`~`, `{working-directory}`, etc.)
   - Generate appropriate Scheme rules for each config section

6. **Temporary File Creation**

   - Write Scheme profile to temporary file (`.sb` suffix)
   - File is not deleted (left for debugging)

7. **Environment Setup**

   - Set `SANDBOX_MODE_NETWORK` environment variable
   - Copy existing environment variables

8. **Command Execution**
   - If command provided: resolve executable path, wrap in `/bin/sh -c`
   - If no command: use `$SHELL` or `/bin/sh` for interactive shell
   - Execute `sandbox-exec -f <profile> <command>`
   - Exit with command's exit code

### Shell Execution Strategy

The CLI uses `/bin/sh` to wrap commands because:

- `/bin/sh` is more likely to be allowed by sandbox profiles
- Custom shells (zsh, fish) may not be in allowed paths
- Provides consistent execution environment

## Development Setup

### Prerequisites

- Python 3.11+
- `uv` package manager (recommended) or pip
- macOS (required for `sandbox-exec`)

### Installation

**From source:**

```bash
git clone <repo-url>
cd sandboxtron
uv tool install -e .
```

**Using uv:**

```bash
uv tool install sbx
```

**Development mode:**

```bash
make install-dev  # Installs with dev dependencies
```

### Project Structure

```
sandboxtron/
├── sbx/                    # Main package
│   ├── __init__.py        # Version info
│   ├── cli.py             # CLI entry point
│   ├── models.py          # Pydantic data models
│   ├── profile_generator.py # Profile loading/merging/Scheme generation
│   ├── install.py         # Profile installation helper
│   └── profiles/          # Built-in profiles
│       ├── base.toml
│       ├── online.toml
│       ├── app.toml
│       ├── gui.toml
│       ├── file-full.toml
│       └── uv_tools.toml
├── pyproject.toml         # Project metadata and dependencies
├── Makefile              # Development commands
├── README.md             # User documentation
└── AGENTS.md             # This file
```

### Dependencies

**Runtime:**

- `pydantic>=2.12.4`: Data validation and models
- `rich>=14.2.0`: Terminal output formatting (for install messages)
- `tomllib`: Built-in Python 3.11+ (or `tomli>=2.0.0` for older Python)

**Development:**

- `basedpyright>=1.32.1`: Type checking
- `ruff>=0.14.4`: Linting and formatting
- `pyupgrade>=3.21.0`: Code modernization

### Development Commands

```bash
make help              # Show all available commands
make install           # Install package
make install-dev       # Install with dev dependencies
make lint              # Run ruff linter
make format            # Format code with ruff
make type-check        # Run basedpyright type checker
make check-all         # Run lint + type-check
make clean             # Remove build artifacts
make build             # Build distribution packages
make verify            # Verify installation works
```

### Type Checking

The project uses `basedpyright` (Pyright fork) for type checking. Configuration in `pyrightconfig.json`:

- Python 3.13 target
- Darwin platform
- Strict import checking
- Excludes `__pycache__` directories

## Testing & Debugging

### Testing Sandbox Profiles

1. **Check Console.app**: Search for "sandbox" to see denied permissions
2. **Use log command**:
   ```bash
   log show --predicate 'process == "kernel" AND message CONTAINS "deny"' --info --debug --last 3m
   ```
3. **Inspect generated Scheme**: Temporary `.sb` files are left in `/tmp/` for inspection

### Common Issues

**"deny forbidden-sandbox-reinit"**:

- Some applications (Electron, `swift build`) try to reinitialize the sandbox
- This is a known limitation (see README TODO)

**Executable not found**:

- CLI resolves executables via `shutil.which()`
- Ensure executable is in `PATH` before sandbox execution

**Profile not found**:

- Check `~/.local/config/sbx/profiles/` for user profiles
- Check `sbx/profiles/` for package profiles
- Run `sbx --install-profiles` to copy defaults

### Debugging Tips

1. **Inspect generated Scheme**: Check `/tmp/` for `.sb` files
2. **Test profiles individually**: `sbx base -- echo "test"`
3. **Use overrides**: `sbx +network.enabled=true -- curl https://example.com`
4. **Check environment**: `sbx -- env | grep SANDBOX`

## Known Limitations & TODOs

### Current Limitations

1. **Executable-specific profiles**: Mentioned in README but not implemented

   - Would require parsing `executables.toml` and matching executable names
   - Would need to integrate with command resolution logic

2. **Sandbox reinit errors**: Some apps fail with `forbidden-sandbox-reinit`

   - Electron apps
   - `swift build` (though `swift` REPL works)

3. **Temporary file cleanup**: Generated `.sb` files are not deleted
   - Could accumulate in `/tmp/`
   - Consider cleanup on successful execution

### Potential Enhancements

1. **Profile validation**: Validate TOML structure before execution
2. **Profile caching**: Cache generated Scheme files for performance
3. **Better error messages**: More descriptive errors for common issues
4. **Profile inheritance**: Explicit profile inheritance mechanism
5. **Profile testing**: Dry-run mode to validate profiles without execution

## Code Patterns & Conventions

### Type Hints

- Uses Python 3.11+ type hints throughout
- `ProfileOverrides` is a type alias for nested dictionaries
- Pydantic models provide runtime type validation

### Error Handling

- `FileNotFoundError` raised for missing profiles
- Errors printed to `stderr` and exit with code 1
- Uses `sys.exit()` for clean termination

### Path Handling

- Uses `pathlib.Path` for path operations
- Supports both absolute and relative paths
- Handles home directory expansion (`~`)
- Supports regex patterns in paths

### Configuration Merging

- Deep merge algorithm handles nested dictionaries
- Lists are concatenated (not replaced)
- Later values override earlier ones
- Command-line overrides have highest precedence

## Contributing Guidelines

### Adding a New Profile

1. Create `sbx/profiles/new-profile.toml`
2. Follow existing profile structure
3. Document in README if it's a general-purpose profile
4. Test with: `sbx new-profile -- <test-command>`

### Modifying Core Logic

1. **Profile loading**: Modify `ProfileGenerator.load_profile()`
2. **Merging logic**: Modify `ProfileGenerator._deep_merge()`
3. **Scheme generation**: Modify `ProfileGenerator.generate_scheme()`
4. **CLI parsing**: Modify `cli.py:parse_overrides()` or `cli.py:main()`

### Adding New Configuration Options

1. Add model fields to appropriate `*Config` class in `models.py`
2. Add Scheme generation logic in `profile_generator.py:generate_scheme()`
3. Update profile examples if needed
4. Document in README

### Code Style

- Follow existing code style (checked by `ruff`)
- Use type hints for all functions
- Keep functions focused and small
- Add docstrings for public APIs

## External Resources

- [macOS App Sandboxing via sandbox-exec](https://www.karltarvas.com/2020/10/25/macos-app-sandboxing-via-sandbox-exec.html)
- [Original writeup](https://kevinlynagh.com/newsletter/2020_04_how_fast_can_plants_grow/)
- Apple's built-in profiles: `/System/Library/Sandbox/Profiles/`
- Scheme sandbox profile syntax: See Apple's documentation and example profiles

## Quick Reference

### Key Files

- `sbx/cli.py`: CLI entry point and execution logic
- `sbx/profile_generator.py`: Profile loading, merging, and Scheme generation
- `sbx/models.py`: Pydantic data models
- `sbx/profiles/base.toml`: Default profile (most important)

### Key Functions

- `cli.main()`: Main entry point
- `ProfileGenerator.load_profile()`: Load TOML profile
- `ProfileGenerator.merge_profiles()`: Merge multiple profiles
- `ProfileGenerator.generate_scheme()`: Convert to Scheme syntax
- `cli.parse_overrides()`: Parse command-line overrides

### Common Tasks

**Add a new profile**: Create `.toml` file in `sbx/profiles/`
**Modify merging logic**: Edit `ProfileGenerator._deep_merge()`
**Add new config option**: Add field to model, add Scheme generation
**Debug profile**: Check `/tmp/` for generated `.sb` files

---

This document should provide everything a developer needs to understand and contribute to the sbx project. For user-facing documentation, see `README.md`.
