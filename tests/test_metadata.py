"""Tests for GGUF metadata reader."""

import struct
import tempfile
from pathlib import Path

import pytest

from justllama.models.metadata import (
    GGUFMetadata,
    get_model_info_summary,
    get_model_training_context,
    read_gguf_metadata,
    _GGUF_MAGIC,
)


def _create_mock_gguf(
    tmp_path: Path,
    metadata: dict | None = None,
    version: int = 3,
) -> Path:
    """Create a minimal mock GGUF file with the given metadata.

    This creates a valid GGUF header with metadata but no tensors.
    """
    path = tmp_path / "test_model.gguf"

    with open(path, "wb") as f:
        # Magic number
        f.write(struct.pack("<I", _GGUF_MAGIC))
        # Version
        f.write(struct.pack("<I", version))
        # Tensor count (0 for our mock)
        f.write(struct.pack("<Q", 0))

        if metadata is None:
            metadata = {}

        # Metadata KV count
        f.write(struct.pack("<Q", len(metadata)))

        # Write each key-value pair
        for key, value in metadata.items():
            # Write key (string: uint64 length + bytes)
            key_bytes = key.encode("utf-8")
            f.write(struct.pack("<Q", len(key_bytes)))
            f.write(key_bytes)

            # Determine value type and write
            if isinstance(value, int):
                # INT64
                f.write(struct.pack("<I", 11))  # value type
                f.write(struct.pack("<q", value))
            elif isinstance(value, float):
                # FLOAT64
                f.write(struct.pack("<I", 12))  # value type
                f.write(struct.pack("<d", value))
            elif isinstance(value, str):
                # STRING
                f.write(struct.pack("<I", 8))  # value type
                str_bytes = value.encode("utf-8")
                f.write(struct.pack("<Q", len(str_bytes)))
                f.write(str_bytes)
            elif isinstance(value, bool):
                # BOOL
                f.write(struct.pack("<I", 7))  # value type
                f.write(struct.pack("<?", value))
            else:
                raise ValueError(f"Unsupported value type: {type(value)}")

    return path


class TestReadGGUFMetadata:
    """Tests for read_gguf_metadata function."""

    def test_read_empty_metadata(self, tmp_path):
        """Test reading a GGUF file with no metadata."""
        path = _create_mock_gguf(tmp_path, metadata={})
        result = read_gguf_metadata(str(path))
        assert result == {}

    def test_read_string_metadata(self, tmp_path):
        """Test reading string metadata values."""
        metadata = {
            "general.architecture": "llama",
            "general.name": "Test Model",
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        result = read_gguf_metadata(str(path))
        assert result["general.architecture"] == "llama"
        assert result["general.name"] == "Test Model"

    def test_read_int_metadata(self, tmp_path):
        """Test reading integer metadata values."""
        metadata = {
            "llama.context_length": 32768,
            "llama.block_count": 32,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        result = read_gguf_metadata(str(path))
        assert result["llama.context_length"] == 32768
        assert result["llama.block_count"] == 32

    def test_read_mixed_metadata(self, tmp_path):
        """Test reading mixed type metadata."""
        metadata = {
            "general.architecture": "gemma",
            "gemma.context_length": 8192,
            "gemma.block_count": 28,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        result = read_gguf_metadata(str(path))
        assert result["general.architecture"] == "gemma"
        assert result["gemma.context_length"] == 8192
        assert result["gemma.block_count"] == 28

    def test_file_not_found(self):
        """Test error handling for non-existent file."""
        with pytest.raises(FileNotFoundError):
            read_gguf_metadata("/nonexistent/path/model.gguf")

    def test_invalid_magic(self, tmp_path):
        """Test error handling for invalid GGUF magic number."""
        path = tmp_path / "invalid.gguf"
        with open(path, "wb") as f:
            f.write(b"NOT_GGUF")
        with pytest.raises(ValueError, match="Not a GGUF file"):
            read_gguf_metadata(str(path))

    def test_file_too_small(self, tmp_path):
        """Test error handling for file too small to be valid GGUF."""
        path = tmp_path / "tiny.gguf"
        with open(path, "wb") as f:
            f.write(b"GG")
        with pytest.raises(ValueError, match="too small"):
            read_gguf_metadata(str(path))


class TestGetModelTrainingContext:
    """Tests for get_model_training_context function."""

    def test_llama_context(self, tmp_path):
        """Test extracting llama model context length."""
        metadata = {
            "general.architecture": "llama",
            "llama.context_length": 4096,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        assert get_model_training_context(str(path)) == 4096

    def test_gemma_context(self, tmp_path):
        """Test extracting gemma model context length."""
        metadata = {
            "general.architecture": "gemma",
            "gemma.context_length": 8192,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        assert get_model_training_context(str(path)) == 8192

    def test_large_context(self, tmp_path):
        """Test extracting large context length (e.g., 128K)."""
        metadata = {
            "general.architecture": "llama",
            "llama.context_length": 131072,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        assert get_model_training_context(str(path)) == 131072

    def test_no_context_in_metadata(self, tmp_path):
        """Test returning 0 when context length is not in metadata."""
        metadata = {
            "general.architecture": "llama",
            # No context_length key
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        assert get_model_training_context(str(path)) == 0

    def test_file_not_found(self):
        """Test returning 0 for non-existent file."""
        assert get_model_training_context("/nonexistent/model.gguf") == 0


class TestGetModelInfoSummary:
    """Tests for get_model_info_summary function."""

    def test_full_info(self, tmp_path):
        """Test getting full model info summary."""
        metadata = {
            "general.architecture": "llama",
            "general.name": "Test Llama Model",
            "llama.context_length": 32768,
            "llama.block_count": 32,
            "tokenizer.chat_template": "{% for message in messages %}{{ message.content }}{% endfor %}",
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        info = get_model_info_summary(str(path))

        assert info["architecture"] == "llama"
        assert info["name"] == "Test Llama Model"
        assert info["context_length"] == 32768
        assert info["block_count"] == 32
        assert info["has_chat_template"] is True
        # File size is >= 0 (mock files are tiny, may round to 0.0)
        assert info["file_size_gb"] >= 0

    def test_no_metadata(self, tmp_path):
        """Test getting info from file with no metadata."""
        path = _create_mock_gguf(tmp_path, metadata={})
        info = get_model_info_summary(str(path))

        assert info["architecture"] == ""
        assert info["name"] == ""
        assert info["context_length"] == 0
        assert info["block_count"] == 0
        assert info["has_chat_template"] is False

    def test_file_not_found(self, tmp_path):
        """Test getting info for non-existent file."""
        info = get_model_info_summary("/nonexistent/model.gguf")
        assert info["architecture"] == ""
        assert info["context_length"] == 0

    def test_chat_template_detection_llama(self, tmp_path):
        """Test detecting llama chat template."""
        metadata = {
            "tokenizer.chat_template": "{% if messages[0]['role'] == 'system' %}llama_format{% endif %}",
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        info = get_model_info_summary(str(path))
        assert info["has_chat_template"] is True
        assert info["chat_template_name"] == "llama"

    def test_chat_template_detection_gemma(self, tmp_path):
        """Test detecting gemma chat template."""
        metadata = {
            # Use a template string that contains "gemma" for detection
            "tokenizer.chat_template": "gemma_format: <start_of_turn>user\n{{ message.content }}<end_of_turn>",
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        info = get_model_info_summary(str(path))
        assert info["has_chat_template"] is True
        assert info["chat_template_name"] == "gemma"

    def test_moe_detection_by_architecture(self, tmp_path):
        """Test detecting MoE models by architecture name."""
        for arch in ["mixtral", "qwen2moe", "qwen3moe", "dbrx", "jamba", "arctic"]:
            metadata = {
                "general.architecture": arch,
                f"{arch}.block_count": 32,
            }
            path = _create_mock_gguf(tmp_path, metadata=metadata)
            info = get_model_info_summary(str(path))
            assert info["is_moe"] is True, f"Failed to detect MoE for architecture: {arch}"

    def test_moe_detection_by_expert_count(self, tmp_path):
        """Test detecting MoE models by expert_count metadata."""
        metadata = {
            "general.architecture": "llama",
            "llama.block_count": 32,
            "llama.expert_count": 8,
            "llama.expert_used_count": 2,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        info = get_model_info_summary(str(path))
        assert info["is_moe"] is True
        assert info["expert_count"] == 8
        assert info["expert_used_count"] == 2

    def test_non_moe_model(self, tmp_path):
        """Test that non-MoE models are correctly identified."""
        metadata = {
            "general.architecture": "llama",
            "llama.block_count": 32,
            "llama.context_length": 4096,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)
        info = get_model_info_summary(str(path))
        assert info["is_moe"] is False
        assert info["expert_count"] == 0
        assert info["expert_used_count"] == 0


class TestGGUFMetadataQML:
    """Tests for GGUFMetadata QML-accessible class."""

    def test_read_metadata_slot(self, tmp_path):
        """Test the read_metadata QML slot."""
        metadata = {"general.architecture": "test_arch"}
        path = _create_mock_gguf(tmp_path, metadata=metadata)

        qml_obj = GGUFMetadata()
        result = qml_obj.read_metadata(str(path))
        assert result["general.architecture"] == "test_arch"

    def test_read_metadata_error(self):
        """Test read_metadata returns empty dict on error."""
        qml_obj = GGUFMetadata()
        result = qml_obj.read_metadata("/nonexistent/model.gguf")
        assert result == {}

    def test_get_context_length_slot(self, tmp_path):
        """Test the get_context_length QML slot."""
        metadata = {
            "general.architecture": "llama",
            "llama.context_length": 16384,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)

        qml_obj = GGUFMetadata()
        result = qml_obj.get_context_length(str(path))
        assert result == 16384

    def test_get_model_info_slot(self, tmp_path):
        """Test the get_model_info QML slot."""
        metadata = {
            "general.architecture": "mistral",
            "mistral.context_length": 8192,
            "mistral.block_count": 32,
        }
        path = _create_mock_gguf(tmp_path, metadata=metadata)

        qml_obj = GGUFMetadata()
        result = qml_obj.get_model_info(str(path))
        assert result["architecture"] == "mistral"
        assert result["context_length"] == 8192
        assert result["block_count"] == 32
