from __future__ import annotations

import os
import sys
import types


def test_load_sentence_transformer_retries_on_cpu_after_cuda_oom(monkeypatch):
    from langchain_app.core import embedding_loader

    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_ref, device=None):
            calls.append((model_ref, device))
            if device != "cpu":
                raise RuntimeError("CUDA out of memory. Tried to allocate 978.00 MiB.")
            self.model_ref = model_ref
            self.device = device

    monkeypatch.delenv("PYTORCH_CUDA_ALLOC_CONF", raising=False)
    monkeypatch.delenv("LANGCHAIN_APP_EMBED_DEVICE", raising=False)
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_DEVICE", raising=False)
    monkeypatch.setattr(embedding_loader.sys, "platform", "linux")
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    model = embedding_loader.load_sentence_transformer("demo-model")

    assert calls == [("demo-model", "cpu")]
    assert model.device == "cpu"
    assert embedding_loader.resolve_sentence_transformer_device() == "cpu"
    assert "expandable_segments:True" in os.environ["PYTORCH_CUDA_ALLOC_CONF"]


def test_configure_torch_cuda_allocator_skips_windows(monkeypatch):
    from langchain_app.core import embedding_loader

    monkeypatch.delenv("PYTORCH_CUDA_ALLOC_CONF", raising=False)
    monkeypatch.setattr(embedding_loader.sys, "platform", "win32")

    embedding_loader.configure_torch_cuda_allocator()

    assert "PYTORCH_CUDA_ALLOC_CONF" not in os.environ


def test_load_sentence_transformer_respects_explicit_cpu_device(monkeypatch):
    from langchain_app.core import embedding_loader

    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_ref, device=None):
            calls.append((model_ref, device))
            self.device = device

    monkeypatch.setenv("LANGCHAIN_APP_EMBED_DEVICE", "cpu")
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    model = embedding_loader.load_sentence_transformer("demo-model")

    assert calls == [("demo-model", "cpu")]
    assert model.device == "cpu"


def test_load_sentence_transformer_can_use_explicit_cuda_then_fallback(monkeypatch):
    from langchain_app.core import embedding_loader

    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model_ref, device=None):
            calls.append((model_ref, device))
            if device == "cuda":
                raise RuntimeError("CUDA out of memory. Tried to allocate 978.00 MiB.")
            self.device = device

    monkeypatch.setenv("LANGCHAIN_APP_EMBED_DEVICE", "cuda")
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    model = embedding_loader.load_sentence_transformer("demo-model")

    assert calls == [("demo-model", "cuda"), ("demo-model", "cpu")]
    assert model.device == "cpu"


def test_vector_db_sentence_transformer_embeddings_uses_shared_loader(monkeypatch):
    from langchain_app.core.vector_db import _SentenceTransformerEmbeddings

    seen = {}

    class FakeModel:
        def encode(self, texts, convert_to_numpy=True):
            return [0.1]

    def fake_loader(model_name, *, offline=False):
        seen["model_name"] = model_name
        seen["offline"] = offline
        return FakeModel()

    monkeypatch.setattr("langchain_app.core.vector_db.load_sentence_transformer", fake_loader)

    embedder = _SentenceTransformerEmbeddings("shared-model")

    assert seen == {"model_name": "shared-model", "offline": False}
    assert embedder.model.__class__ is FakeModel
