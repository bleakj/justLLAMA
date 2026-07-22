"""Per-model configuration profiles stored as JSON on disk."""

import json
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from justllama.models.metadata import get_model_training_context


def _get_total_vram_gb() -> float:
    """Get total GPU VRAM in GB via nvidia-smi. Returns 0 if unavailable."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, check=True, timeout=5
        )
        return int(result.stdout.strip().split('\n')[0]) / 1024.0
    except Exception:
        return 0.0


def _estimate_model_vram_gb(model_path: str) -> float:
    """Estimate model VRAM usage from file size (rough approximation)."""
    try:
        size_gb = Path(model_path).stat().st_size / (1024**3)
        # Model needs ~file_size + overhead for computation buffers
        return size_gb + 1.0
    except Exception:
        return 0.0


def _vram_based_ctx_cap(model_path: str, model_draft: str = "", n_gpu_layers=99) -> int:
    """Calculate maximum context size that safely fits in available VRAM.

    This is a HARD safety cap — it always runs to prevent OOM regardless of
    what ctx_size the user or profile requested.

    Estimates:
      available_vram = total_vram - model_vram - draft_vram - buffer
      max_ctx = available_vram / kv_cache_per_token

    The buffer is generous (2.5 GB) to account for:
      - KV cache growth during conversation
      - MTP/speculative decoding overhead
      - CUDA allocation fragmentation
      - System display / compositor VRAM usage

    Args:
        model_path: Path to the main GGUF model file.
        model_draft: Path to draft model for speculative decoding (empty if none).
        n_gpu_layers: Number of GPU layers (99 or "auto" = all).

    Returns:
        Maximum safe context size in tokens, or 0 if VRAM can't be determined.
    """
    total_vram = _get_total_vram_gb()
    if total_vram <= 0:
        return 0  # Can't determine — no NVIDIA GPU or nvidia-smi unavailable

    model_vram = _estimate_model_vram_gb(model_path)

    # Account for draft model VRAM (MTP / speculative decoding)
    draft_vram = 0.0
    if model_draft:
        draft_vram = _estimate_model_vram_gb(model_draft)

    # Generous buffer for KV cache growth, MTP overhead, CUDA fragmentation,
    # and display/compositor usage. 2.5 GB is the minimum safe margin.
    buffer_gb = 2.5

    available_vram = total_vram - model_vram - draft_vram - buffer_gb

    if available_vram <= 0:
        # Model barely fits — use minimal context
        return 2048

    # If not all layers are on GPU, reduce the VRAM pressure proportionally.
    # When n_gpu_layers is "auto" or 99, assume all layers go to GPU (worst case).
    gpu_fraction = 1.0
    if isinstance(n_gpu_layers, int) and 0 < n_gpu_layers < 99:
        # Estimate fraction of model on GPU
        try:
            from justllama.models.metadata import get_model_info_summary
            info = get_model_info_summary(model_path)
            total_layers = info.get("block_count", 0)
            if total_layers > 0:
                gpu_fraction = min(1.0, n_gpu_layers / total_layers)
        except Exception:
            gpu_fraction = 1.0  # Can't determine — assume worst case

    # KV cache per token estimate based on model file size.
    # The KV cache lives in VRAM when flash_attn is on and layers are on GPU.
    # Rough: each layer stores 2 tensors (K, V) of hidden_size * fp16 per token.
    # We approximate using file size as a proxy for model dimensions.
    model_size_gb = model_vram - 1.0  # Approximate original file size
    if model_size_gb <= 2:
        mb_per_token = 0.15  # ~1-3B params
    elif model_size_gb <= 5:
        mb_per_token = 0.35  # ~7B params
    elif model_size_gb <= 10:
        mb_per_token = 0.6   # ~12-13B params
    elif model_size_gb <= 25:
        mb_per_token = 1.2   # ~30B params
    elif model_size_gb <= 45:
        mb_per_token = 2.0   # ~65-70B params
    else:
        mb_per_token = 3.5   # Very large models

    # Scale by GPU fraction — if only some layers are on GPU, less KV cache in VRAM
    effective_mb_per_token = mb_per_token * gpu_fraction
    if effective_mb_per_token <= 0:
        effective_mb_per_token = mb_per_token  # Fallback

    available_mb = available_vram * 1024
    max_tokens = int(available_mb / effective_mb_per_token)

    # Round down to nearest 1024, minimum 2048
    return max(2048, (max_tokens // 1024) * 1024)


def _compute_safe_ngl(model_path: str, total_vram: float = 0, model_vram: float = 0) -> int:
    """Compute safe number of GPU layers based on VRAM and model type.

    MoE models need much lower NGL because they have many more total parameters
    than active parameters. For example, Mixtral 8x7B has ~47B total params but
    only ~13B active, yet ALL expert weights must be in VRAM when offloaded.

    Args:
        model_path: Path to the GGUF model file.
        total_vram: Total GPU VRam in GB (0 = auto-detect).
        model_vram: Estimated model VRAM in GB (0 = estimate from file size).

    Returns:
        Safe number of GPU layers to offload.
    """
    from justllama.models.metadata import get_model_info_summary

    try:
        info = get_model_info_summary(model_path)
    except Exception:
        return 99  # Can't determine — let llama-server decide

    block_count = info.get("block_count", 0)
    is_moe = info.get("is_moe", False)

    if block_count == 0:
        return 99  # Can't determine

    # Auto-detect VRAM if not provided
    if total_vram <= 0:
        total_vram = _get_total_vram_gb()
    if total_vram <= 0:
        return 99  # Can't determine — no GPU info

    # Estimate model VRAM if not provided
    if model_vram <= 0:
        model_vram = _estimate_model_vram_gb(model_path)

    # Buffer for KV cache, overhead, and safety margin
    buffer_gb = 2.5
    available_vram = total_vram - buffer_gb

    if available_vram <= 0:
        return 0  # Not enough VRAM for model

    # MoE models: be very conservative. MoE models have ALL expert weights in
    # the file, so file size is misleading. They need much lower NGL.
    # User reports MoE models need ~ngl 24 to function properly.
    if is_moe:
        # For MoE: aim for ~60-70% of layers on GPU as maximum
        # This is conservative but prevents OOM
        max_ngl_ratio = 0.65
        
        # Further reduce if model is large relative to VRAM
        model_to_vram_ratio = model_vram / total_vram
        if model_to_vram_ratio > 0.8:
            max_ngl_ratio = 0.4  # Model is huge — be very conservative
        elif model_to_vram_ratio > 0.6:
            max_ngl_ratio = 0.5
        
        safe_ngl = max(1, int(block_count * max_ngl_ratio))
        
        # Hard cap at 24 for MoE models as user reported
        safe_ngl = min(safe_ngl, 24)
        
        return safe_ngl

    # Non-MoE models: more aggressive offloading
    # If model fits comfortably in VRAM, offload all layers
    if model_vram + buffer_gb <= total_vram * 0.85:
        return 99  # Model fits easily — offload all

    # Model is tight on VRAM — reduce layers proportionally
    # Aim for 80% of VRAM usage
    target_vram_usage = total_vram * 0.80
    if model_vram > 0:
        layer_ratio = target_vram_usage / model_vram
        safe_ngl = max(1, int(block_count * min(1.0, layer_ratio)))
        return safe_ngl

    return 99  # Fallback


_PROFILES_DIR = Path.home() / ".config" / "justllama" / "profiles"


class ModelProfiles(QObject):
    """Manages named configuration profiles for server settings.

    Signals:
        profiles_changed()
    """

    profiles_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        _PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_").replace("..", "_")
        return _PROFILES_DIR / f"{safe}.json"
    @Slot(str, str, result=bool)
    def save_profile(self, name: str, config_json: str) -> bool:
        """Save a profile. config_json is a JSON string of settings dict."""
        try:
            config = json.loads(config_json)
        except json.JSONDecodeError:
            return False
        try:
            self._path_for(name).write_text(json.dumps(config, indent=2))
            self.profiles_changed.emit()
            return True
        except OSError:
            return False

    @Slot(str, result=str)
    def load_profile(self, name: str) -> str:
        """Load a profile, returns JSON string or empty string."""
        path = self._path_for(name)
        if path.is_file():
            try:
                return path.read_text()
            except OSError:
                pass
        # Fallback to model filename if name was a full path
        if "/" in name or "\\" in name:
            alt_path = self._path_for(Path(name).name)
            if alt_path.is_file():
                try:
                    return alt_path.read_text()
                except OSError:
                    pass
        return ""

    @Slot(str, result=dict)
    def get_model_profile(self, model_path: str) -> dict:
        """Get model profile as a dictionary for a given model path."""
        raw = self.load_profile(model_path)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @Slot(str, str, result=bool)
    def save_model_profile(self, model_path: str, config_json: str) -> bool:
        """Save a profile JSON string for a given model path."""
        return self.save_profile(model_path, config_json)

    def get_effective_config(self, model_path: str, global_settings=None) -> dict:
        """Return merged config dictionary (global defaults overridden by model profile).

        Smart defaults:
        - ctx_size: 0 = auto-detect from GGUF metadata (uses 75% of training context)
        - n_gpu_layers: "auto" = let llama-server detect VRAM
        - jinja: True = read chat template from GGUF metadata
        """
        # Get global settings with smart defaults
        global_ctx = global_settings.get_int("server/ctx_size") if global_settings else 0
        global_ngl = global_settings.get_string("server/n_gpu_layers") if global_settings else "auto"

        eff = {
            "binary": global_settings.get_string("server/binary") if global_settings else "llama-server",
            "port": global_settings.get_int("server/port") if (global_settings and global_settings.get_int("server/port")) else 8080,
            "model_path": model_path,
            "ctx_size": global_ctx if global_ctx else 0,  # 0 = auto from GGUF
            "n_gpu_layers": global_ngl if global_ngl else "auto",
            "threads": global_settings.get_int("server/threads") if global_settings else -1,
            "batch_size": global_settings.get_int("server/batch_size") if (global_settings and global_settings.get_int("server/batch_size")) else 512,
            "ubatch_size": global_settings.get_int("server/ubatch_size") if (global_settings and global_settings.get_int("server/ubatch_size")) else 512,
            "flash_attn": global_settings.get_bool("server/flash_attn") if global_settings else True,
            "mmap": global_settings.get_bool("server/mmap") if global_settings else True,
            "mlock": global_settings.get_bool("server/mlock") if global_settings else False,
            "cache_type_k": global_settings.get_string("server/cache_type_k") if global_settings else "",
            "cache_type_v": global_settings.get_string("server/cache_type_v") if global_settings else "",
            "cpu_moe": global_settings.get_bool("server/cpu_moe") if global_settings else False,
            "n_cpu_moe": global_settings.get_int("server/n_cpu_moe") if global_settings else 0,
            "model_draft": global_settings.get_string("server/model_draft") if global_settings else "",
            "gpu_layers_draft": global_settings.get_int("server/gpu_layers_draft") if (global_settings and global_settings.get_int("server/gpu_layers_draft")) else 99,
            "draft_max": global_settings.get_int("server/draft_max") if global_settings else 0,
            "draft_min": global_settings.get_int("server/draft_min") if global_settings else 0,
            "jinja": True,  # Enable Jinja by default to read chat template from GGUF
            "chat_template": "",
            "extra_args": [],
        }
        profile = self.get_model_profile(model_path)
        for k, v in profile.items():
            if v is not None and v != "":
                eff[k] = v

        # Smart default: if ctx_size is 0 (auto), read from GGUF metadata
        # and apply a safe fraction (75%) to prevent OOM with KV cache + MTP.
        if eff["ctx_size"] == 0 or eff["ctx_size"] == "0":
            training_ctx = get_model_training_context(model_path)
            if training_ctx > 0:
                # Use 75% of training context to leave room for KV cache overhead
                safe_ctx = int(training_ctx * 0.75)
                # Cap at 32768 as a reasonable upper bound
                safe_ctx = min(safe_ctx, 32768)
            else:
                # Fallback to 8192 if we can't read GGUF metadata
                safe_ctx = 8192
            eff["ctx_size"] = safe_ctx
            eff["_auto_ctx"] = True  # Flag that this was auto-detected

        # ── HARD VRAM SAFETY CAP ──────────────────────────────────────────
        # ALWAYS run this check regardless of how ctx_size was set. This
        # prevents OOM when:
        #   - A saved profile has an explicit ctx_size (e.g. 32768)
        #   - n_gpu_layers is 99 (all layers on GPU, no CPU spillover)
        #   - MTP/draft model is consuming additional VRAM
        #   - The user's VRAM is insufficient for the requested context
        # This cap is non-negotiable: it will reduce ctx_size if needed.
        vram_cap = _vram_based_ctx_cap(
            model_path,
            model_draft=eff.get("model_draft", ""),
            n_gpu_layers=eff.get("n_gpu_layers", 99),
        )
        if vram_cap > 0 and eff["ctx_size"] > vram_cap:
            eff["_ctx_capped_by_vram"] = True
            eff["_ctx_original"] = eff["ctx_size"]
            eff["ctx_size"] = vram_cap

        # ── SMART NGL AUTO-DETECTION ─────────────────────────────────────
        # When n_gpu_layers is "auto" or 99, compute a safe value based on
        # VRAM and model type. MoE models especially need much lower NGL.
        ngl_value = eff.get("n_gpu_layers", "auto")
        if ngl_value in ("auto", "AUTO", 99, -1):
            safe_ngl = _compute_safe_ngl(model_path)
            if safe_ngl != 99:
                eff["_ngl_auto"] = True
                eff["_ngl_original"] = ngl_value
                eff["n_gpu_layers"] = safe_ngl

        return eff

    @Slot(str, QObject, result=str)
    def get_effective_config_json(self, model_path: str, global_settings=None) -> str:
        """Return merged config as a JSON string for QML consumption."""
        eff = self.get_effective_config(model_path, global_settings)
        return json.dumps(eff)
    @Slot(result=list)
    def list_profiles(self) -> list[str]:
        """List all profile names."""
        return sorted(
            p.stem for p in _PROFILES_DIR.glob("*.json")
        )

    @Slot(str, result=bool)
    def delete_profile(self, name: str) -> bool:
        """Delete a profile by name."""
        path = self._path_for(name)
        if path.is_file():
            try:
                path.unlink()
                self.profiles_changed.emit()
                return True
            except OSError:
                return False
        return False
