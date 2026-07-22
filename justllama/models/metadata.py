"""Minimal GGUF metadata reader for extracting model information.

Parses only the GGUF file header (metadata section) without loading tensor data.
This allows auto-detection of model capabilities like context size, architecture,
number of layers, and chat templates before loading the model.

GGUF format reference: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
"""

import struct
from pathlib import Path

from PySide6.QtCore import QObject, Slot


# GGUF magic number: "GGUF" in little-endian (bytes 0x47 0x47 0x55 0x46)
_GGUF_MAGIC = 0x46554747

# GGUF metadata value types
_META_UINT8 = 0
_META_INT8 = 1
_META_UINT16 = 2
_META_INT16 = 3
_META_UINT32 = 4
_META_INT32 = 5
_META_FLOAT32 = 6
_META_BOOL = 7
_META_STRING = 8
_META_ARRAY = 9
_META_UINT64 = 10
_META_INT64 = 11
_META_FLOAT64 = 12

# Map of value type to struct format and size
_TYPE_INFO = {
    _META_UINT8:   ("B", 1),
    _META_INT8:    ("b", 1),
    _META_UINT16:  ("H", 2),
    _META_INT16:   ("h", 2),
    _META_UINT32:  ("I", 4),
    _META_INT32:   ("i", 4),
    _META_FLOAT32: ("f", 4),
    _META_BOOL:    ("?", 1),
    _META_UINT64:  ("Q", 8),
    _META_INT64:   ("q", 8),
    _META_FLOAT64: ("d", 8),
}


def _read_string(f) -> str:
    """Read a GGUF string (uint64 length + UTF-8 bytes)."""
    length_bytes = f.read(8)
    if len(length_bytes) < 8:
        raise ValueError("Unexpected end of file reading string length")
    length = struct.unpack("<Q", length_bytes)[0]
    if length > 10_000_000:  # 10 MB sanity limit
        raise ValueError(f"String too long: {length} bytes")
    data = f.read(length)
    if len(data) < length:
        raise ValueError("Unexpected end of file reading string data")
    return data.decode("utf-8", errors="replace")


def _read_value(f, value_type: int):
    """Read a single metadata value of the given type."""
    if value_type in _TYPE_INFO:
        fmt, size = _TYPE_INFO[value_type]
        data = f.read(size)
        if len(data) < size:
            raise ValueError(f"Unexpected end of file reading value type {value_type}")
        return struct.unpack(f"<{fmt}", data)[0]

    if value_type == _META_STRING:
        return _read_string(f)

    if value_type == _META_ARRAY:
        # Array: element type (uint32) + length (uint64) + elements
        type_data = f.read(4)
        len_data = f.read(8)
        if len(type_data) < 4 or len(len_data) < 8:
            raise ValueError("Unexpected end of file reading array header")
        elem_type = struct.unpack("<I", type_data)[0]
        elem_count = struct.unpack("<Q", len_data)[0]
        if elem_count > 1_000_000:  # Sanity limit
            raise ValueError(f"Array too long: {elem_count} elements")
        return [_read_value(f, elem_type) for _ in range(elem_count)]

    raise ValueError(f"Unknown metadata value type: {value_type}")


def read_gguf_metadata(model_path: str, max_keys: int = 500) -> dict:
    """Read metadata from a GGUF file header.

    Args:
        model_path: Path to the GGUF file.
        max_keys: Maximum number of metadata keys to read (safety limit).

    Returns:
        Dictionary of metadata key-value pairs. Only includes keys we can
        successfully parse; unreadable keys are silently skipped.
    """
    path = Path(model_path)
    if not path.is_file():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    metadata = {}
    with open(path, "rb") as f:
        # Read and verify magic number
        magic = f.read(4)
        if len(magic) < 4:
            raise ValueError("File too small to be a valid GGUF")
        magic_num = struct.unpack("<I", magic)[0]
        if magic_num != _GGUF_MAGIC:
            raise ValueError(f"Not a GGUF file (magic: 0x{magic_num:08X})")

        # Read version
        version_data = f.read(4)
        if len(version_data) < 4:
            raise ValueError("Unexpected end of file reading version")
        version = struct.unpack("<I", version_data)[0]
        if version < 2 or version > 3:
            # Version 2 and 3 are the most common; we support both
            pass  # Continue anyway, best-effort parsing

        # Read tensor count and metadata KV count
        counts_data = f.read(16)
        if len(counts_data) < 16:
            raise ValueError("Unexpected end of file reading counts")
        tensor_count, metadata_kv_count = struct.unpack("<QQ", counts_data)

        # Read metadata key-value pairs
        keys_read = 0
        for _ in range(min(metadata_kv_count, max_keys)):
            try:
                key = _read_string(f)
                value_type_data = f.read(4)
                if len(value_type_data) < 4:
                    break
                value_type = struct.unpack("<I", value_type_data)[0]
                value = _read_value(f, value_type)
                metadata[key] = value
                keys_read += 1
            except (ValueError, struct.error, UnicodeDecodeError):
                # Skip unreadable keys but continue parsing
                break

    return metadata


def get_model_training_context(model_path: str) -> int:
    """Extract the training context length from a GGUF model.

    Searches for context length in common metadata keys across different
    model architectures.

    Returns:
        Training context length, or 0 if not found.
    """
    try:
        meta = read_gguf_metadata(model_path)
    except (FileNotFoundError, ValueError):
        return 0

    # Try architecture-specific context length keys
    arch = meta.get("general.architecture", "")
    context_keys = [
        f"{arch}.context_length",
        "llama.context_length",
        "gemma.context_length",
        "gemma2.context_length",
        "gemma3.context_length",
        "qwen2.context_length",
        "mistral.context_length",
        "phi3.context_length",
        "bloom.context_length",
        "falcon.context_length",
        "general.context_length",
    ]

    for key in context_keys:
        if key in meta:
            try:
                return int(meta[key])
            except (TypeError, ValueError):
                continue

    return 0


def get_model_info_summary(model_path: str) -> dict:
    """Get a summary of model information for UI display.

    Returns:
        Dictionary with keys: architecture, name, context_length, block_count,
        has_chat_template, chat_template_name, file_size_gb, is_moe, expert_count,
        expert_used_count.
    """
    path = Path(model_path)
    info = {
        "architecture": "",
        "name": "",
        "context_length": 0,
        "block_count": 0,
        "has_chat_template": False,
        "chat_template_name": "",
        "file_size_gb": 0.0,
        "is_moe": False,
        "expert_count": 0,
        "expert_used_count": 0,
    }

    if not path.is_file():
        return info

    info["file_size_gb"] = round(path.stat().st_size / (1024**3), 2)

    try:
        meta = read_gguf_metadata(model_path)
    except (FileNotFoundError, ValueError):
        return info

    info["architecture"] = str(meta.get("general.architecture", ""))
    info["name"] = str(meta.get("general.name", ""))

    # Context length
    arch = info["architecture"]
    for key in [f"{arch}.context_length", "general.context_length"]:
        if key in meta:
            try:
                info["context_length"] = int(meta[key])
                break
            except (TypeError, ValueError):
                continue

    # Block count (number of transformer layers)
    for key in [f"{arch}.block_count", "general.block_count"]:
        if key in meta:
            try:
                info["block_count"] = int(meta[key])
                break
            except (TypeError, ValueError):
                continue

    # MoE (Mixture of Experts) detection
    # Check for expert_count in architecture-specific keys
    moe_archs = {"mixtral", "qwen2moe", "qwen3moe", "dbrx", "jamba", "arctic", "gemma4"}
    if arch.lower() in moe_archs:
        info["is_moe"] = True
    
    for key in [f"{arch}.expert_count", "general.expert_count"]:
        if key in meta:
            try:
                expert_count = int(meta[key])
                info["expert_count"] = expert_count
                if expert_count > 0:
                    info["is_moe"] = True
                break
            except (TypeError, ValueError):
                continue
    
    for key in [f"{arch}.expert_used_count", "general.expert_used_count"]:
        if key in meta:
            try:
                info["expert_used_count"] = int(meta[key])
                break
            except (TypeError, ValueError):
                continue

    # Chat template
    template = meta.get("tokenizer.chat_template", "")
    if template:
        info["has_chat_template"] = True
        template_str = str(template)
        # Try to identify the template family
        if "llama" in template_str.lower():
            info["chat_template_name"] = "llama"
        elif "gemma" in template_str.lower():
            info["chat_template_name"] = "gemma"
        elif "chatml" in template_str.lower():
            info["chat_template_name"] = "chatml"
        elif "mistral" in template_str.lower() or "[INST]" in template_str:
            info["chat_template_name"] = "mistral"
        elif "qwen" in template_str.lower():
            info["chat_template_name"] = "qwen"
        elif "phi" in template_str.lower():
            info["chat_template_name"] = "phi"
        else:
            info["chat_template_name"] = "custom"

    return info


class GGUFMetadata(QObject):
    """QML-accessible interface for reading GGUF model metadata.

    Provides methods to extract model information from GGUF files for
    auto-configuration and UI display.
    """

    @Slot(str, result=dict)
    def read_metadata(self, model_path: str) -> dict:
        """Read all metadata from a GGUF file.

        Returns a dictionary of metadata key-value pairs, or empty dict on error.
        """
        try:
            return read_gguf_metadata(model_path)
        except Exception as e:
            print(f"[GGUFMetadata] Error reading {model_path}: {e}")
            return {}

    @Slot(str, result=int)
    def get_context_length(self, model_path: str) -> int:
        """Get the training context length from a GGUF model.

        Returns 0 if the context length cannot be determined.
        """
        return get_model_training_context(model_path)

    @Slot(str, result=dict)
    def get_model_info(self, model_path: str) -> dict:
        """Get a summary of model information for UI display.

        Returns dictionary with: architecture, name, context_length,
        block_count, has_chat_template, chat_template_name, file_size_gb.
        """
        return get_model_info_summary(model_path)
