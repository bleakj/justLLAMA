"""CLI argument builder for llama-server subprocess."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path


def _as_int(value, default: int = 0) -> int:
    """Best-effort int coercion (settings/JSON may hand us strings)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ServerConfig:
    """Configuration for llama-server CLI arguments."""

    binary: str = "llama-server"
    model_path: str = ""
    port: int = 8080
    ctx_size: int = 4096
    n_gpu_layers: int | str = "auto"
    threads: int = -1  # -1 = auto
    batch_size: int = 512
    ubatch_size: int = 512
    flash_attn: bool | str = "on"
    fit: bool = False  # --fit off: disable auto-fit to device memory (we manage VRAM ourselves)
    mmap: bool = True
    mlock: bool = False
    numa: str = ""  # "disabled", "numactl", "isolate", "distribute"
    jinja: bool = False
    chat_template: str = ""
    # KV cache quantization ("", "f16", "q8_0", "q4_0", ...). Default q8_0 saves VRAM.
    cache_type_k: str = "q8_0"
    cache_type_v: str = "q8_0"
    # Mixture-of-Experts expert offload to CPU. n_cpu_moe > 0 offloads the
    # experts of that many layers; cpu_moe offloads ALL experts. n_cpu_moe wins
    # if both are set.
    cpu_moe: bool = False
    n_cpu_moe: int = 0
    # Speculative decoding draft model. Only emitted when model_draft is set.
    model_draft: str = ""
    gpu_layers_draft: int = 99
    draft_max: int = 0
    draft_min: int = 0
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

        # ctx_size of 0 means auto-detect from GGUF metadata (handled by manager)
        if self.ctx_size != 0 and self.ctx_size < 256:
            errors.append(f"Context size must be >= 256 or 0 for auto, got {self.ctx_size}")

        return errors

    def build_command(self) -> list[str]:
        """Build the full CLI command list."""
        if self.n_gpu_layers in (99, -1, "auto", "AUTO") or str(self.n_gpu_layers).lower() == "auto":
            ngl_str = "auto"
        else:
            ngl_str = str(self.n_gpu_layers)

        cmd = [
            self.binary,
            "--model", self.model_path,
            "--port", str(self.port),
            "--ctx-size", str(self.ctx_size),
            "--n-gpu-layers", ngl_str,
            "--batch-size", str(self.batch_size),
            "--ubatch-size", str(self.ubatch_size),
        ]

        if self.threads > 0:
            cmd.extend(["--threads", str(self.threads)])

        if isinstance(self.flash_attn, bool):
            fa_val = "on" if self.flash_attn else "off"
        else:
            fa_val = str(self.flash_attn).lower() if self.flash_attn else "off"

        if fa_val in ("on", "off", "auto"):
            cmd.extend(["--flash-attn", fa_val])
        elif fa_val:
            cmd.extend(["--flash-attn", fa_val])

        # --fit: auto-adjust params to fit in device memory
        cmd.extend(["--fit", "on" if self.fit else "off"])

        # Enable Jinja by default for automatic chat template from GGUF
        if self.jinja:
            cmd.append("--jinja")

        if self.chat_template:
            cmd.extend(["--chat-template", str(self.chat_template)])

        if self.mlock:
            cmd.append("--mlock")
        elif not self.mmap:
            cmd.append("--no-mmap")

        if self.numa:
            cmd.extend(["--numa", self.numa])

        # KV cache quantization
        if self.cache_type_k:
            cmd.extend(["--cache-type-k", str(self.cache_type_k)])
        if self.cache_type_v:
            cmd.extend(["--cache-type-v", str(self.cache_type_v)])

        # MoE expert offload to CPU (n_cpu_moe takes precedence over cpu_moe)
        n_cpu_moe = _as_int(self.n_cpu_moe)
        if n_cpu_moe > 0:
            cmd.extend(["--n-cpu-moe", str(n_cpu_moe)])
        elif self.cpu_moe:
            cmd.append("--cpu-moe")

        # Speculative decoding draft model
        if self.model_draft:
            cmd.extend(["--model-draft", str(self.model_draft)])
            cmd.extend(["--gpu-layers-draft", str(_as_int(self.gpu_layers_draft, 99))])
            draft_max = _as_int(self.draft_max)
            if draft_max > 0:
                cmd.extend(["--spec-draft-n-max", str(draft_max)])
            draft_min = _as_int(self.draft_min)
            if draft_min > 0:
                cmd.extend(["--spec-draft-n-min", str(draft_min)])

        if isinstance(self.extra_args, str):
            cmd.extend(self.extra_args.split())
        else:
            cmd.extend(self.extra_args)

        return cmd
    @classmethod
    def from_dict(cls, d: dict) -> ServerConfig:
        """Create from a settings dict."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {}
        for k, v in d.items():
            if k in known_fields:
                filtered[k] = v
        if "extra_args" in filtered and isinstance(filtered["extra_args"], str):
            filtered["extra_args"] = filtered["extra_args"].split()
        return cls(**filtered)
