"""Tests for justllama.server.config.ServerConfig."""

from unittest.mock import patch

import pytest

from justllama.server.config import ServerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_config(**overrides) -> ServerConfig:
    """Return a config that passes validation by default."""
    defaults = dict(
        binary="llama-server",
        model_path="/fake/model.gguf",
        port=8080,
        ctx_size=4096,
   )
    defaults.update(overrides)
    return ServerConfig(**defaults)


# ---------------------------------------------------------------------------
# validate() — valid config
# ---------------------------------------------------------------------------

class TestValidateValid:
    def test_valid_config_returns_no_errors(self, tmp_path):
        model = tmp_path / "model.gguf"
        model.write_text("")
        cfg = _valid_config(model_path=str(model))

        with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
            errors = cfg.validate()

        assert errors == []

    def test_valid_config_all_defaults(self, tmp_path):
        """Full default config with a real model and binary still passes."""
        model = tmp_path / "model.gguf"
        model.write_text("")

        with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
            cfg = ServerConfig(model_path=str(model))
            errors = cfg.validate()

        assert errors == []


# ---------------------------------------------------------------------------
# validate() — model_path errors
# ---------------------------------------------------------------------------

class TestValidateModelPath:
    def test_missing_model_path(self):
        cfg = _valid_config(model_path="")
        errors = cfg.validate()
        assert any("No model path" in e for e in errors)

    def test_nonexistent_model_file(self):
        cfg = _valid_config(model_path="/nonexistent/path/model.gguf")
        errors = cfg.validate()
        assert any("not found" in e for e in errors)

    def test_model_path_is_directory_not_file(self, tmp_path):
        """A directory at model_path should be rejected (is_file returns False)."""
        cfg = _valid_config(model_path=str(tmp_path))
        errors = cfg.validate()
        assert any("not found" in e for e in errors)


# ---------------------------------------------------------------------------
# validate() — port errors
# ---------------------------------------------------------------------------

class TestValidatePort:
    @pytest.mark.parametrize("bad_port", [0, 80, 500, 1023, 65536, 70000, 99999])
    def test_port_out_of_range(self, bad_port):
        cfg = _valid_config(port=bad_port)
        errors = cfg.validate()
        assert any("Port must be 1024-65535" in e for e in errors)

    @pytest.mark.parametrize("good_port", [1024, 8080, 30000, 65535])
    def test_port_in_range(self, good_port):
        model = "fake.gguf"
        cfg = _valid_config(port=good_port)
        # Mock binary so only port is tested in isolation (model won't exist,
        # but we care that the port check *doesn't* add an error).
        with patch("justllama.server.config.Path.is_file", return_value=True):
            with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
                errors = cfg.validate()
        assert not any("Port" in e for e in errors)


# ---------------------------------------------------------------------------
# validate() — ctx_size errors
# ---------------------------------------------------------------------------

class TestValidateCtxSize:
    # ctx_size=0 is now valid (auto-detect from GGUF metadata)
    @pytest.mark.parametrize("bad_size", [1, 100, 255])
    def test_ctx_size_too_small(self, bad_size):
        cfg = _valid_config(ctx_size=bad_size)
        errors = cfg.validate()
        assert any("Context size" in e for e in errors)

    def test_ctx_size_zero_is_valid_auto(self):
        """ctx_size=0 means auto-detect from GGUF metadata."""
        cfg = _valid_config(ctx_size=0)
        with patch("justllama.server.config.Path.is_file", return_value=True):
            with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
                errors = cfg.validate()
        assert not any("Context size" in e for e in errors)

    def test_ctx_size_exactly_256_is_valid(self):
        cfg = _valid_config(ctx_size=256)
        with patch("justllama.server.config.Path.is_file", return_value=True):
            with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
                errors = cfg.validate()
        assert not any("Context size" in e for e in errors)


# ---------------------------------------------------------------------------
# validate() — binary not found
# ---------------------------------------------------------------------------

class TestValidateBinary:
    def test_binary_not_on_path_and_not_file(self):
        cfg = _valid_config()
        with patch("justllama.server.config.shutil.which", return_value=None):
            with patch("justllama.server.config.Path.is_file", return_value=False):
                errors = cfg.validate()
        assert any("binary not found" in e for e in errors)

    def test_binary_found_on_path(self):
        cfg = _valid_config()
        with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
            with patch("justllama.server.config.Path.is_file", return_value=True):
                errors = cfg.validate()
        assert not any("binary not found" in e for e in errors)

    def test_binary_not_on_path_but_is_file(self):
        """Custom binary path that is a real file on disk."""
        cfg = _valid_config(binary="/opt/custom/llama-server")
        with patch("justllama.server.config.shutil.which", return_value=None):
            with patch("justllama.server.config.Path.is_file", return_value=True):
                errors = cfg.validate()
        assert not any("binary not found" in e for e in errors)


# ---------------------------------------------------------------------------
# validate() — multiple errors accumulate
# ---------------------------------------------------------------------------

    def test_all_bad_returns_all_errors(self):
        """Config with bad model, bad binary, bad port, and bad ctx_size."""
        cfg = ServerConfig(port=100, ctx_size=128)
        with patch("justllama.server.config.shutil.which", return_value=None):
            with patch("justllama.server.config.Path.is_file", return_value=False):
                errors = cfg.validate()
        # model path, binary, port, ctx_size
        assert len(errors) >= 4


# ---------------------------------------------------------------------------
# build_command() — base command
# ---------------------------------------------------------------------------

class TestBuildCommand:
    def test_default_command_structure(self):
        cfg = _valid_config()
        cmd = cfg.build_command()

        assert cmd[0] == "llama-server"
        assert "--model" in cmd
        assert "/fake/model.gguf" in cmd
        assert "--port" in cmd
        assert "8080" in cmd
        assert "--ctx-size" in cmd
        assert "4096" in cmd
        assert "--n-gpu-layers" in cmd
        assert "auto" in cmd
        assert "--batch-size" in cmd
        assert "512" in cmd
        assert "--ubatch-size" in cmd

    def test_command_is_list_of_strings(self):
        cfg = _valid_config()
        cmd = cfg.build_command()
        assert isinstance(cmd, list)
        assert all(isinstance(c, str) for c in cmd)


# ---------------------------------------------------------------------------
# build_command() — flash_attn
# ---------------------------------------------------------------------------

class TestBuildCommandFlashAttn:
    def test_flash_attn_true_adds_flag(self):
        cfg = _valid_config(flash_attn=True)
        cmd = cfg.build_command()
        idx = cmd.index("--flash-attn")
        assert cmd[idx + 1] == "on"

    def test_flash_attn_false_sets_off(self):
        cfg = _valid_config(flash_attn=False)
        cmd = cfg.build_command()
        idx = cmd.index("--flash-attn")
        assert cmd[idx + 1] == "off"

    def test_flash_attn_auto_sets_auto(self):
        cfg = _valid_config(flash_attn="auto")
        cmd = cfg.build_command()
        idx = cmd.index("--flash-attn")
        assert cmd[idx + 1] == "auto"

    def test_jinja_and_chat_template_flags(self):
        cfg = _valid_config(jinja=True, chat_template="chatml")
        cmd = cfg.build_command()
        assert "--jinja" in cmd
        idx = cmd.index("--chat-template")
        assert cmd[idx + 1] == "chatml"
# ---------------------------------------------------------------------------
# build_command() — mlock / mmap
# ---------------------------------------------------------------------------

class TestBuildCommandMlockMmap:
    def test_mlock_true_adds_flag(self):
        cfg = _valid_config(mlock=True, mmap=True)
        cmd = cfg.build_command()
        assert "--mlock" in cmd
        assert "--no-mmap" not in cmd

    def test_mlock_false_no_mmap_true_omits_both(self):
        """mlock=False, mmap=True → neither --mlock nor --no-mmap."""
        cfg = _valid_config(mlock=False, mmap=True)
        cmd = cfg.build_command()
        assert "--mlock" not in cmd
        assert "--no-mmap" not in cmd

    def test_mlock_false_no_mmap_adds_no_mmap(self):
        """mlock=False, mmap=False → --no-mmap."""
        cfg = _valid_config(mlock=False, mmap=False)
        cmd = cfg.build_command()
        assert "--mlock" not in cmd
        assert "--no-mmap" in cmd

    def test_mlock_true_mmap_false_uses_mlock(self):
        """mlock=True takes precedence even when mmap=False."""
        cfg = _valid_config(mlock=True, mmap=False)
        cmd = cfg.build_command()
        assert "--mlock" in cmd
        assert "--no-mmap" not in cmd


# ---------------------------------------------------------------------------
# build_command() — performance knobs (KV cache / MoE offload / draft)
# ---------------------------------------------------------------------------

class TestBuildCommandPerformanceKnobs:
    def test_cache_type_flags(self):
        cfg = _valid_config(cache_type_k="q8_0", cache_type_v="q4_0")
        cmd = cfg.build_command()
        assert cmd[cmd.index("--cache-type-k") + 1] == "q8_0"
        assert cmd[cmd.index("--cache-type-v") + 1] == "q4_0"

    def test_cache_type_empty_omits(self):
        cfg = _valid_config(cache_type_k="", cache_type_v="")
        cmd = cfg.build_command()
        assert "--cache-type-k" not in cmd
        assert "--cache-type-v" not in cmd

    def test_fit_flag_off_by_default(self):
        cfg = _valid_config()
        cmd = cfg.build_command()
        idx = cmd.index("--fit")
        assert cmd[idx + 1] == "off"

    def test_fit_flag_on(self):
        cfg = _valid_config(fit=True)
        cmd = cfg.build_command()
        idx = cmd.index("--fit")
        assert cmd[idx + 1] == "on"

    def test_cpu_moe_flag(self):
        cfg = _valid_config(cpu_moe=True)
        cmd = cfg.build_command()
        assert "--cpu-moe" in cmd
        assert "--n-cpu-moe" not in cmd

    def test_n_cpu_moe_takes_precedence(self):
        cfg = _valid_config(cpu_moe=True, n_cpu_moe=24)
        cmd = cfg.build_command()
        assert cmd[cmd.index("--n-cpu-moe") + 1] == "24"
        assert "--cpu-moe" not in cmd

    def test_n_cpu_moe_string_coerced(self):
        cfg = _valid_config(n_cpu_moe="18")
        cmd = cfg.build_command()
        assert cmd[cmd.index("--n-cpu-moe") + 1] == "18"

    def test_moe_omitted_by_default(self):
        cfg = _valid_config()
        cmd = cfg.build_command()
        assert "--cpu-moe" not in cmd
        assert "--n-cpu-moe" not in cmd

    def test_draft_model_flags(self):
        cfg = _valid_config(
            model_draft="/fake/draft.gguf",
            gpu_layers_draft=99,
            draft_max=16,
            draft_min=2,
        )
        cmd = cfg.build_command()
        assert cmd[cmd.index("--model-draft") + 1] == "/fake/draft.gguf"
        assert cmd[cmd.index("--gpu-layers-draft") + 1] == "99"
        assert cmd[cmd.index("--spec-draft-n-max") + 1] == "16"
        assert cmd[cmd.index("--spec-draft-n-min") + 1] == "2"

    def test_draft_omitted_when_no_model(self):
        cfg = _valid_config(draft_max=16, draft_min=2)
        cmd = cfg.build_command()
        assert "--model-draft" not in cmd
        assert "--gpu-layers-draft" not in cmd
        assert "--spec-draft-n-max" not in cmd


# ---------------------------------------------------------------------------
# build_command() — threads
# ---------------------------------------------------------------------------

class TestBuildCommandThreads:
    def test_threads_positive_adds_flag(self):
        cfg = _valid_config(threads=8)
        cmd = cfg.build_command()
        idx = cmd.index("--threads")
        assert cmd[idx + 1] == "8"

    def test_threads_negative_omits_flag(self):
        cfg = _valid_config(threads=-1)
        cmd = cfg.build_command()
        assert "--threads" not in cmd

    def test_threads_zero_omits_flag(self):
        """threads=0 is treated as auto (not > 0), so flag is omitted."""
        cfg = _valid_config(threads=0)
        cmd = cfg.build_command()
        assert "--threads" not in cmd


# ---------------------------------------------------------------------------
# build_command() — numa
# ---------------------------------------------------------------------------

class TestBuildCommandNuma:
    def test_numa_empty_omits_flag(self):
        cfg = _valid_config(numa="")
        cmd = cfg.build_command()
        assert "--numa" not in cmd

    @pytest.mark.parametrize("numa_val", ["disabled", "numactl", "isolate", "distribute"])
    def test_numa_value_adds_flag(self, numa_val):
        cfg = _valid_config(numa=numa_val)
        cmd = cfg.build_command()
        idx = cmd.index("--numa")
        assert cmd[idx + 1] == numa_val


# ---------------------------------------------------------------------------
# build_command() — extra_args
# ---------------------------------------------------------------------------

class TestBuildCommandExtraArgs:
    def test_extra_args_appended(self):
        cfg = _valid_config(extra_args=["--host", "0.0.0.0", "--verbose"])
        cmd = cfg.build_command()
        assert cmd[-3:] == ["--host", "0.0.0.0", "--verbose"]

    def test_empty_extra_args(self):
        cfg = _valid_config(extra_args=[])
        cmd = cfg.build_command()
        # Should not have trailing empty strings
        assert cmd[-1] != ""

    def test_extra_args_after_all_built_in_args(self):
        cfg = _valid_config(extra_args=["--foo", "bar"])
        cmd = cfg.build_command()
        # Extra args come after everything else
        assert cmd[-2] == "--foo"
        assert cmd[-1] == "bar"


# ---------------------------------------------------------------------------
# build_command() — custom values
# ---------------------------------------------------------------------------

class TestBuildCommandCustomValues:
    def test_custom_binary(self):
        cfg = _valid_config(binary="/custom/path/llama-server")
        cmd = cfg.build_command()
        assert cmd[0] == "/custom/path/llama-server"

    def test_custom_model_path(self):
        cfg = _valid_config(model_path="/data/models/mistral.gguf")
        cmd = cfg.build_command()
        assert "/data/models/mistral.gguf" in cmd

    def test_custom_port_and_ctx(self):
        cfg = _valid_config(port=9090, ctx_size=8192)
        cmd = cfg.build_command()
        port_idx = cmd.index("--port")
        ctx_idx = cmd.index("--ctx-size")
        assert cmd[port_idx + 1] == "9090"
        assert cmd[ctx_idx + 1] == "8192"

    def test_custom_gpu_layers(self):
        cfg = _valid_config(n_gpu_layers=0)
        cmd = cfg.build_command()
        idx = cmd.index("--n-gpu-layers")
        assert cmd[idx + 1] == "0"

    def test_custom_batch_sizes(self):
        cfg = _valid_config(batch_size=1024, ubatch_size=256)
        cmd = cfg.build_command()
        bs_idx = cmd.index("--batch-size")
        ubs_idx = cmd.index("--ubatch-size")
        assert cmd[bs_idx + 1] == "1024"
        assert cmd[ubs_idx + 1] == "256"


# ---------------------------------------------------------------------------
# build_command() — combined flags
# ---------------------------------------------------------------------------

class TestBuildCommandCombined:
    def test_all_flags_together(self):
        cfg = _valid_config(
            threads=16,
            flash_attn=True,
            mlock=True,
            numa="isolate",
            extra_args=["--log-disable"],
        )
        cmd = cfg.build_command()
        assert "--threads" in cmd
        assert "--flash-attn" in cmd
        assert "--mlock" in cmd
        assert "--numa" in cmd
        assert "--log-disable" in cmd

    def test_mlock_prevents_no_mmap_even_with_flash(self):
        """Regression: mlock + flash_attn should not produce --no-mmap."""
        cfg = _valid_config(mlock=True, mmap=False, flash_attn=True)
        cmd = cfg.build_command()
        assert "--no-mmap" not in cmd
        assert "--mlock" in cmd
        assert "--flash-attn" in cmd


# ---------------------------------------------------------------------------
# from_dict()
# ---------------------------------------------------------------------------

class TestFromDict:
    def test_creates_config_from_valid_dict(self):
        d = {
            "binary": "/usr/bin/custom-server",
            "model_path": "/models/test.gguf",
            "port": 9090,
            "ctx_size": 2048,
            "n_gpu_layers": 33,
            "threads": 8,
            "flash_attn": False,
            "mmap": False,
            "mlock": True,
            "numa": "isolate",
            "extra_args": ["--verbose"],
        }
        cfg = ServerConfig.from_dict(d)

        assert cfg.binary == "/usr/bin/custom-server"
        assert cfg.model_path == "/models/test.gguf"
        assert cfg.port == 9090
        assert cfg.ctx_size == 2048
        assert cfg.n_gpu_layers == 33
        assert cfg.threads == 8
        assert cfg.flash_attn is False
        assert cfg.mmap is False
        assert cfg.mlock is True
        assert cfg.numa == "isolate"
        assert cfg.extra_args == ["--verbose"]

    def test_ignores_unknown_keys(self):
        d = {
            "model_path": "/m.gguf",
            "port": 8080,
            "unknown_field": "should_be_ignored",
            "another_unknown": 42,
        }
        cfg = ServerConfig.from_dict(d)
        assert cfg.model_path == "/m.gguf"
        assert cfg.port == 8080
        # Unknown keys should not raise and not appear as attributes
        assert not hasattr(cfg, "unknown_field")

    def test_handles_partial_dict(self):
        d = {"port": 3000}
        cfg = ServerConfig.from_dict(d)

        # Specified value is set
        assert cfg.port == 3000
        # All other fields use dataclass defaults
        assert cfg.binary == "llama-server"
        assert cfg.model_path == ""
        assert cfg.ctx_size == 4096
        assert cfg.n_gpu_layers == "auto"
        assert cfg.threads == -1
        assert cfg.flash_attn == "on"
        assert cfg.jinja is False
        assert cfg.chat_template == ""
        assert cfg.mmap is True
        assert cfg.mlock is False
        assert cfg.numa == ""
        assert cfg.extra_args == []

    def test_empty_dict_uses_all_defaults(self):
        cfg = ServerConfig.from_dict({})
        default = ServerConfig()
        assert cfg.binary == default.binary
        assert cfg.model_path == default.model_path
        assert cfg.port == default.port
        assert cfg.ctx_size == default.ctx_size
        assert cfg.n_gpu_layers == default.n_gpu_layers
        assert cfg.threads == default.threads
        assert cfg.flash_attn == default.flash_attn
        assert cfg.mmap == default.mmap
        assert cfg.mlock == default.mlock
        assert cfg.numa == default.numa
        assert cfg.extra_args == default.extra_args

    def test_from_dict_build_command_round_trip(self):
        """Config built from dict should produce the same command as direct construction."""
        d = {"model_path": "/m.gguf", "port": 5000, "threads": 4, "flash_attn": False}
        cfg_from_dict = ServerConfig.from_dict(d)
        cfg_direct = ServerConfig(model_path="/m.gguf", port=5000, threads=4, flash_attn=False)

        assert cfg_from_dict.build_command() == cfg_direct.build_command()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_validate_empty_model_path_with_real_tmp_file(self, tmp_path):
        """Ensure validate checks model_path string, not just file existence."""
        model = tmp_path / "test.gguf"
        model.write_text("dummy")
        cfg = _valid_config(model_path="")
        errors = cfg.validate()
        assert any("No model path" in e for e in errors)

    def test_build_command_preserves_order(self):
        """Core flags appear in a predictable order."""
        cfg = _valid_config(threads=4, numa="numactl")
        cmd = cfg.build_command()

        # Find positions
        model_idx = cmd.index("--model")
        port_idx = cmd.index("--port")
        ctx_idx = cmd.index("--ctx-size")
        gpu_idx = cmd.index("--n-gpu-layers")

        assert model_idx < port_idx < ctx_idx < gpu_idx

    def test_validate_with_real_model_file(self, tmp_path):
        """Integration-style: validate passes with real file and mocked binary."""
        model = tmp_path / "real_model.gguf"
        model.write_text("fake content")
        cfg = _valid_config(model_path=str(model))

        with patch("justllama.server.config.shutil.which", return_value="/usr/bin/llama-server"):
            errors = cfg.validate()

        assert errors == []
