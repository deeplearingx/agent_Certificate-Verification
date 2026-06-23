# 无关

This folder contains old implementations, experiments, backups, and legacy tests that are not part of the current LangGraph/LangChain mainline.

Current mainline code lives in `langchain_app/`. Do not import code from `无关/` into the mainline. If a legacy implementation is useful, migrate the logic into `langchain_app/` and add or update tests under `tests/`.

## Folders

| Folder | Contents |
| --- | --- |
| `01_legacy_modules/` | Old root-level packages such as `core`, `checks`, `config`, `kb`, `llm` |
| `02_apps_and_demos/` | Old UI/app/demo scripts |
| `03_parsing_legacy/` | Old PDF, Markdown, pdfplumber, Camelot, PaddleOCR parser experiments |
| `04_verification_legacy/` | Old `*_check.py` and `param_check*.py` verification implementations |
| `05_tests_legacy/` | Old test scripts that predate the current `tests/` suite |
| `06_tools_legacy/` | Old utility scripts such as model download, CNAS fixes, batch verification |

## Current Equivalents

| Legacy folder | Current location |
| --- | --- |
| `01_legacy_modules/core` | `langchain_app/core/` |
| `01_legacy_modules/checks` and `04_verification_legacy` | `langchain_app/checks/` |
| `01_legacy_modules/config` | `langchain_app/utils/config.py` |
| `01_legacy_modules/kb` | `langchain_app/retrieval/`, `langchain_app/core/vector_db.py` |
| `01_legacy_modules/llm` | `langchain_app/core/llm_client.py` |
| `03_parsing_legacy` | `langchain_app/services/` |
| `05_tests_legacy` | `tests/` |

