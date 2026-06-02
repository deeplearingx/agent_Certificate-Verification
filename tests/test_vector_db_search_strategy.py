from langchain_core.documents import Document

from langchain_app.core.vector_db import VectorDatabase


def _build_db():
    db = VectorDatabase.__new__(VectorDatabase)
    db.collection_name = "test"
    db.persist_directory = "/tmp/test-db"
    db.embedding_model_name = "dummy"
    db.embedding_model = None
    db._fallback_cache = None
    db._collection = None
    db._vector_store = None
    db._embedding_init_error = None
    return db


class _FakeCollection:
    def __init__(self, *, query_result=None, query_error=None, count_value=None, pages=None):
        self.query_result = query_result
        self.query_error = query_error
        self.count_value = count_value
        self.pages = pages or {}

    def query(self, **kwargs):
        if self.query_error is not None:
            raise self.query_error
        return self.query_result

    def count(self):
        if self.count_value is None:
            raise RuntimeError("count unavailable")
        return self.count_value

    def get(self, *, limit, offset, include):
        return self.pages[offset]


def test_similarity_search_prefers_vector_query(monkeypatch):
    db = _build_db()
    collection = _FakeCollection(
        query_result={
            "documents": [["vector-doc"]],
            "metadatas": [[{"source": "vector"}]],
            "distances": [[0.25]],
        }
    )

    monkeypatch.setattr(db, "_open_raw_collection", lambda: collection)
    monkeypatch.setattr(db, "_get_query_embedding", lambda query: [0.1, 0.2, 0.3])

    def _unexpected_manual(*args, **kwargs):
        raise AssertionError("manual fallback should not run when vector query succeeds")

    monkeypatch.setattr(db, "_manual_similarity_search", _unexpected_manual)

    docs = db.similarity_search("query", k=1)

    assert len(docs) == 1
    assert docs[0].page_content == "vector-doc"
    assert docs[0].metadata["source"] == "vector"
    assert docs[0].metadata["distance"] == 0.25


def test_similarity_search_falls_back_to_manual_matching(monkeypatch):
    db = _build_db()
    collection = _FakeCollection(query_error=RuntimeError("vector query failed"))

    monkeypatch.setattr(db, "_open_raw_collection", lambda: collection)
    monkeypatch.setattr(db, "_get_query_embedding", lambda query: [0.1, 0.2, 0.3])

    fallback_doc = Document(page_content="manual-doc", metadata={"source": "manual", "distance": 0.2})
    monkeypatch.setattr(
        db,
        "_manual_similarity_search",
        lambda query, k, filter_condition=None: [(fallback_doc, 3.0)],
    )

    docs = db.similarity_search("query", k=1)
    scored = db.similarity_search_with_score("query", k=1)

    assert len(docs) == 1
    assert docs[0].page_content == "manual-doc"
    assert scored == [(fallback_doc, 3.0)]


def test_load_records_reads_persisted_collection_in_pages(monkeypatch):
    db = _build_db()
    total = 10005
    pages = {}
    page_size = 1000
    for offset in range(0, total, page_size):
        end = min(offset + page_size, total)
        pages[offset] = {
            "documents": [f"doc-{i}" for i in range(offset, end)],
            "metadatas": [{"row": i} for i in range(offset, end)],
        }
    collection = _FakeCollection(
        count_value=total,
        pages=pages,
    )

    monkeypatch.setattr(db, "_open_raw_collection", lambda: collection)

    records = db._load_records()

    assert len(records) == total
    assert records[0][0] == "doc-0"
    assert records[-1][0] == "doc-10004"
