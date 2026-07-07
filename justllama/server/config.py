"""CLI argument builder for llama-server subprocess."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerConfig:
    """Configuration for llama-server CLI arguments."""

    binary: str = "llama-server"
    model_path: str = ""
    port: int = 8080
    ctx_size: int = 4096
    n_gpu_layers: int = 99
    threads: int = -1  # -1 = auto
    batch_size: int = 512
    ubatch_size: int = 512
    flash_attn: bool = True
    mmap: bool = True
    mlock: bool = False
    numa: str = ""  # "disabled", "numactl", "isolate", "distribute"
    extra_args: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Return list of validation error messages (empty = OK)."""
        errors = []
        if not self.model_path:
            errors.append("No model path configured")
        elif not Path(self.model_path).is_file():
            errors.append(f"Model file not found: {self.model_path}")

        binary_path = shutil.which(self.binary)
        if not binary_path and not Path(self.binary).is_file():
            errors.append(f"llama-server binary not found: {self.binary}")

        if not (1024 <= self.port <= 65535):
            errors.append(f"Port must be 1024-65535, got {self.port}")

        if self.ctx_size < 256:
            errors.append(f"Context size must be >= 256, got {self.ctx_size}")

        return errors

    def build_command(self) -> list[str]:
        """Build the full CLI command list."""
        cmd = [
            self.binary,
            "--model", self.model_path,
            "--port", str(self.port),
            "--ctx-size", str(self.ctx_size),
            "--n-gpu-layers", str(self.n_gpu_layers),
            "--batch-size", str(self.batch_size),
            "--ubatch-size", str(self.ubatch_size),
        ]

        if self.threads > 0:
            cmd.extend(["--threads", str(self.threads)])

        if self.flash_attn:
            cmd.append("--flash-attn")

        if self.mlock:
            cmd.append("--mlock")
        elif not self.mmap:
            cmd.append("--no-mmap")

        if self.numa:
            cmd.extend(["--numa", self.numa])

        cmd.extend(self.extra_args)
        return cmd

    @classmethod
    def from_dict(cls, d: dict) -> ServerConfig:
        """Create from a settings dict."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known_fields})
