"""Executable regression tests for the critical bugs tracked in ANALYSIS.md.

Each test encodes the *correct* behavior and is marked ``xfail(strict=True)``
while the bug is unfixed: the suite stays green today, and the moment a bug is
fixed the test XPASSes and fails the run, prompting removal of its marker.

Covered:
- BUG-1: VectorStore.clear() leaves a deleted collection handle bound.
- BUG-2: _restore_server crashes on get_int("server/n_gpu_layers") == "auto",
  so llama-server is never restored after image/video generation.
- BUG-3: ComfyUI health check polls a non-existent /health endpoint, and the
  imagegen/videogen health-failure branches fall through to _post_prompt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from justllama.rag.vectorstore import VectorStore
from justllama.server import comfy_helpers
from justllama.server import imagegen as imagegen_mod
from justllama.server import videogen as videogen_mod
from justllama.server.imagegen import ImageGenRunner
from justllama.server.videogen import VideoGenRunner


# ---------------------------------------------------------------------------
# BUG-1 — VectorStore.clear() stale collection handle
# ---------------------------------------------------------------------------

class _FakeCollection:
    """Mimics ChromaDB collection semantics: dies when its name is deleted."""

    def __init__(self, name):
        self.name = name
        self.deleted = False
        self._ids = []

    def add(self, ids, documents, metadatas):
        if self.deleted:
            raise RuntimeError(f"Collection {self.name} does not exist.")
        self._ids.extend(ids)

    def count(self):
        if self.deleted:
            raise RuntimeError(f"Collection {self.name} does not exist.")
        return len(self._ids)


class _FakeClient:
    """Mimics ChromaDB client: get_or_create returns the *existing* live
    collection object; delete_collection invalidates it."""

    def __init__(self):
        self._collections = {}

    def get_or_create_collection(self, name, metadata=None):
        col = self._collections.get(name)
        if col is None or col.deleted:
            col = _FakeCollection(name)
            self._collections[name] = col
        return col

    def delete_collection(self, name):
        col = self._collections.pop(name)
        col.deleted = True


@pytest.mark.xfail(
    reason="BUG-1 (ANALYSIS.md): clear() binds the pre-delete collection "
    "handle, so the next add_documents hits a deleted collection",
    strict=True,
)
def test_vectorstore_add_after_clear_uses_live_collection(qapp, tmp_path):
    store = VectorStore(store_path=str(tmp_path / "vectordb"))
    client = _FakeClient()
    store._client = client
    store._collection = client.get_or_create_collection("justllama")

    assert store.add_documents('[{"text": "hello"}]') == 1
    store.clear()
    # After a correct clear, the bound collection is live and usable.
    assert store.add_documents('[{"text": "world"}]') == 1
    assert store.count() == 1


# ---------------------------------------------------------------------------
# BUG-2 — _restore_server crashes on n_gpu_layers="auto"
# ---------------------------------------------------------------------------

class _AutoGpuSettings:
    """Reproduces AppSettings semantics with the shipped defaults, where
    server/n_gpu_layers defaults to the string "auto" and get_int() does a
    bare int() conversion (settings.py)."""

    _values = {
        "server/binary": "/usr/bin/true",
        "server/model_path": "/tmp/model.gguf",
        "server/port": 8080,
        "server/ctx_size": 0,
        "server/n_gpu_layers": "auto",  # shipped default (settings.py)
        "server/threads": -1,
    }

    def get_string(self, key):
        return str(self._values.get(key, ""))

    def get_int(self, key):
        return int(self._values.get(key, 0))  # int("auto") -> ValueError


@pytest.mark.parametrize("runner_cls, module", [
    (ImageGenRunner, imagegen_mod),
    (VideoGenRunner, videogen_mod),
])
@pytest.mark.xfail(
    reason="BUG-2 (ANALYSIS.md): get_int('server/n_gpu_layers') raises "
    "ValueError on the default 'auto', so the server is never restored",
    strict=True,
)
def test_restore_server_handles_auto_gpu_layers(qapp, monkeypatch,
                                                runner_cls, module):
    from justllama.config import settings as settings_mod
    monkeypatch.setattr(settings_mod, "AppSettings", _AutoGpuSettings)

    server_manager = MagicMock()
    server_manager.start.return_value = True
    runner = runner_cls("prompt", {}, "model", server_manager)

    runner._restore_server(True)  # must not raise on the "auto" default

    assert server_manager.start.called


# ---------------------------------------------------------------------------
# BUG-3 — ComfyUI health check: wrong endpoint and missing early return
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason="BUG-3 (ANALYSIS.md): ComfyUI exposes no /health endpoint "
    "(use /system_stats), so every launch waits the full timeout",
    strict=True,
)
def test_health_url_targets_an_existing_comfyui_endpoint():
    assert not comfy_helpers.HEALTH_URL.endswith("/health")


@pytest.mark.parametrize("runner_cls, module", [
    (ImageGenRunner, imagegen_mod),
    (VideoGenRunner, videogen_mod),
])
@pytest.mark.xfail(
    reason="BUG-3 (ANALYSIS.md): the health-failure branch lacks an early "
    "return, so _post_prompt runs against a dead ComfyUI",
    strict=True,
)
def test_execute_aborts_prompt_after_failed_health_check(qapp, monkeypatch,
                                                         runner_cls, module):
    server_manager = MagicMock()
    server_manager.is_running.return_value = False
    runner = runner_cls("prompt", {}, "model", server_manager)

    monkeypatch.setattr(module, "launch_comfyui", lambda: MagicMock())
    monkeypatch.setattr(module, "wait_for_comfy_health", lambda proc, t: False)
    monkeypatch.setattr(module, "stop_comfyui", lambda proc: None)
    posted = []
    monkeypatch.setattr(runner, "_post_prompt",
                        lambda proc: posted.append(proc) or None)

    runner._execute()  # health check fails -> generation must not be posted

    assert posted == []
