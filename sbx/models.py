"""Pydantic models for sandbox profile configuration."""

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

# Type alias for override dictionaries (nested structure matching ProfileConfig)
# Used for command-line overrides
ProfileOverrides = dict[str, Any]  # type: ignore[type-arg]


class ImportsConfig(BaseModel):
    """Configuration for importing system profiles."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    system_profiles: list[str] = []


class NetworkConfig(BaseModel):
    """Network access configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    enabled: bool = False
    allow_localhost: bool = False


class FilesystemReadConfig(BaseModel):
    """Filesystem read access configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    paths: list[str] = []
    regex: list[str] = []


class FilesystemWriteConfig(BaseModel):
    """Filesystem write access configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    paths: list[str] = []
    regex: list[str] = []


class FilesystemConfig(BaseModel):
    """Filesystem access configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    default_deny: bool = False
    read: FilesystemReadConfig | None = None
    write: FilesystemWriteConfig | None = None


class ProcessConfig(BaseModel):
    """Process control configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    allow_exec: bool = False
    allow_fork: bool = False


class SystemConfig(BaseModel):
    """System-level permissions configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    allow_user_preferences: bool = False
    allow_sysctl_write: bool = False
    allow_system_debug: bool = False
    allow_mach_priv_task_port: bool = False


class MachConfig(BaseModel):
    """Mach port lookup configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    lookup: list[str] = []
    lookup_regex: list[str] = []


class IpcConfig(BaseModel):
    """IPC configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    allow_posix_shm: bool = False
    posix_shm_names: list[str] = []
    allow_posix_sem: bool = False


class SignalConfig(BaseModel):
    """Signal handling configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    target: str | None = None


class IokitConfig(BaseModel):
    """IOKit configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    open: list[str] = []


class ProfileConfig(BaseModel):
    """Complete sandbox profile configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    imports: ImportsConfig | None = None
    network: NetworkConfig | None = None
    filesystem: FilesystemConfig | None = None
    process: ProcessConfig | None = None
    system: SystemConfig | None = None
    mach: MachConfig | None = None
    ipc: IpcConfig | None = None
    signal: SignalConfig | None = None
    iokit: IokitConfig | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileConfig":
        """Create ProfileConfig from a dictionary (e.g., from TOML)."""
        # Pydantic automatically handles nested model parsing based on type annotations
        return cls.model_validate(data)

    def to_dict(self) -> dict[str, Any]:  # type: ignore[type-arg]
        """Convert ProfileConfig to a dictionary."""
        # Pydantic automatically handles nested model serialization
        # exclude_unset=True ensures we only include explicitly set values (not defaults)
        # exclude_none=True ensures we don't include None values
        return self.model_dump(exclude_none=True, exclude_unset=True)
