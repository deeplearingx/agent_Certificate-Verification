# scripts_by_part

This folder groups legacy root-level scripts by project responsibility. These scripts are kept for reading, comparison, or one-off rebuilding work. The current mainline remains `langchain_app/`.

Do not import from this folder in mainline code. If useful logic is needed, migrate it into the matching `langchain_app/` module and add tests.

## Folders

| Folder | Contents | Current owner |
| --- | --- | --- |
| `02_parsing_legacy/` | Early PDF parsing, PDF recognition, and PDF-to-vector experiments | Parsing group |
| `03_rag_kb_legacy/` | CNAS, temperature, address, cycle vector database build/search scripts | RAG group |
| `04_verification_legacy/` | Early integrity, basis, environment, location, and cycle verification scripts | Verification group |

## Mainline Replacements

| Legacy area | Mainline location |
| --- | --- |
| PDF / Markdown / JSON parsing | `langchain_app/services/` |
| RAG and vector search | `langchain_app/retrieval/`, `langchain_app/core/vector_db.py` |
| Verification rules | `langchain_app/checks/` |
| LangGraph orchestration | `langchain_app/graph/` |

