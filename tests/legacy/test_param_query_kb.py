import builtins

import param_check


class _FakeEmbedder:
    class _FakeVector:
        def tolist(self):
            return [[0.1, 0.2, 0.3]]

    def encode(self, texts):
        return self._FakeVector()


class _FakeCollection:
    def __init__(self):
        self.last_n_results = None

    def count(self):
        return 5

    def query(self, *, query_embeddings, n_results, include):
        self.last_n_results = n_results
        return {
            "documents": [[
                "doc1", "doc2", "doc3", "doc4", "doc5"
            ]],
            "metadatas": [[
                {"file_code": "JJF 2196"},
                {"file_code": "JJF 2196"},
                {"file_code": "JJF 2196"},
                {"file_code": "JJF 2196"},
                {"file_code": "JJF 9999"},
            ]]
        }


def test_query_kb_returns_all_entries_for_same_basis(monkeypatch):
    coll = _FakeCollection()
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    def fake_parse_kb_entry(doc, meta):
        return {
            "file_code": meta["file_code"],
            "standard_name": meta["file_code"],
            "instrument_name": "频率计",
            "measured": doc,
            "measure_range_text": "-",
            "uncertainty": {"type": "N/A", "value": "N/A"},
        }

    monkeypatch.setattr(param_check, "parse_kb_entry", fake_parse_kb_entry)

    entries = param_check.query_kb(
        coll=coll,
        embedder=_FakeEmbedder(),
        instrument_name="频率计",
        criterion="JJF 2196-2025",
        topk=2,
    )

    assert coll.last_n_results == 5
    assert len(entries) == 4
    assert all(entry["file_code"] == "JJF 2196" for entry in entries)
