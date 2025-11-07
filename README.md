# sbx

A wrapper around Mac's `sandbox-exec` that lets you easily run terminals/programs within sandboxes for a slightly safer day-to-day computing experience.

Useful if you don't want every npm/cargo/pip transitive dependency to have full access to your filesystem and network.

See [this writeup](https://kevinlynagh.com/newsletter/2020_04_how_fast_can_plants_grow/) for a bit more background.

## Features

- **TOML-based profiles**: Easy-to-read and edit configuration files instead of Scheme syntax
- **Profile composition**: Combine multiple profiles and merge them intelligently
- **Executable matching**: Automatically apply profiles based on executable name patterns
- **Command-line overrides**: Fine-tune profiles on the fly with `+key=value` syntax
- **User configuration**: Profiles stored in `~/.local/share/sbx/` for easy customization

## Install

Install using `uv`:

```bash
uv tool install sbx
```

Or install from source:

```bash
git clone <repo-url>
cd sbx
uv tool install -e .
```

Make sure `~/.local/bin` is in your PATH.

## Usage

### Basic Usage

- `sbx` or `sb` opens a shell in an offline sandbox that can only read/write the current directory and its children.

- `sbx online` or `sb online` opens a shell in an online sandbox.

- `sbx online -- ping www.google.com` runs `ping www.google.com` in an online sandbox and returns.

- `sbx foo bar baz -- command` combines profiles `foo`, `bar`, and `baz` and runs `command` within that sandbox.

### Command-Line Overrides

Override profile settings on the command line:

```bash
sbx +network.enabled=true -- curl https://example.com
sbx base +filesystem.write.paths='["/tmp"]' -- mycommand
```

### Custom Profiles

Create custom profiles in `~/.local/config/sbx/profiles/`:

```toml
[profile]
name = "my-custom"
description = "My custom profile"

[network]
enabled = true

[filesystem.write]
paths = ["~/.myapp"]
```

Then use it: `sbx my-custom -- myapp`

### Environment Variables

When running in a sandbox, the following env vars will be defined:

- `SANDBOX_MODE_NETWORK`
  - `online` - network access enabled
  - `offline` - network access disabled (localhost only)

## Profile Format

Profiles are defined in TOML format. See `sbx/profiles/` for examples.

Key sections:

- `[network]` - Network access configuration
- `[filesystem]` - File system read/write permissions
- `[process]` - Process execution and forking
- `[system]` - System-level permissions
- `[mach]` - Mach port lookups
- `[ipc]` - Inter-process communication
- `[signal]` - Signal handling

## Troubleshooting

If an app doesn't work in a sandbox, search for "sandbox" in `Console.app` to see what permissions the app was denied and try granting these permissions via a custom profile.

Alternatively, use the cli:

```bash
log show --predicate 'process == "kernel" AND message CONTAINS "deny" AND  message CONTAINS "<app-name>"' --info --debug --last 3m
```

## Todo

- `deny forbidden-sandbox-reinit` is thrown by:
  - Electron
  - `swift build` (though `swift` starts a REPL just fine)

## Further reading

- https://www.karltarvas.com/2020/10/25/macos-app-sandboxing-via-sandbox-exec.html
- Take a look around Apple's built-in profiles in /System/Library/Sandbox/Profiles
