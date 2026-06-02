# Copyright (c) Opendatalab. All rights reserved.
import copy
import os
from pathlib import Path

from loguru import logger

from langchain_app.utils.runtime_cache import apply_default_windows_ai_cache_env

apply_default_windows_ai_cache_env()

try:
    from mineru.cli.common import convert_pdf_bytes_to_bytes_by_pypdfium2, prepare_env, read_fn
except ImportError:
    from mineru.cli.common import prepare_env, read_fn

    convert_pdf_bytes_to_bytes_by_pypdfium2 = None
from mineru.data.data_reader_writer import FileBasedDataWriter
from mineru.utils.engine_utils import get_vlm_engine
from mineru.utils.enum_class import MakeMode
from mineru.backend.vlm.vlm_analyze import doc_analyze as vlm_doc_analyze
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make
from mineru.backend.hybrid.hybrid_analyze import doc_analyze as hybrid_doc_analyze
from mineru.utils.guess_suffix_or_lang import guess_suffix_by_path


def _apply_default_lmdeploy_kwargs(backend: str, kwargs: dict) -> dict:
    """Keep hybrid/vlm parsing on lmdeploy pytorch backend unless explicitly overridden.

    `hybrid-auto-engine` remains the parsing strategy; we only avoid the
    turbomind VLM loading path that currently drops `offload_folder` before it
    reaches `accelerate.load_checkpoint_and_dispatch(...)`.
    """
    normalized_backend = str(backend or "").strip().lower()
    if not (
        normalized_backend.startswith("hybrid-")
        or normalized_backend.startswith("vlm-")
    ):
        return kwargs

    normalized_kwargs = dict(kwargs or {})
    env_backend = str(os.getenv("MINERU_LMDEPLOY_BACKEND", "") or "").strip()
    normalized_lmdeploy_backend = str(
        normalized_kwargs.setdefault("lmdeploy_backend", env_backend or "pytorch")
    ).strip().lower()
    if normalized_lmdeploy_backend == "pytorch":
        normalized_kwargs.pop("offload_folder", None)
    return normalized_kwargs


def _apply_default_mineru_runtime_env(backend: str) -> None:
    """Stabilize MinerU hybrid parsing on small/medium VRAM unless caller overrides it.

    The recent failure mode on 8GB VRAM is Hybrid auto-selecting batch_ratio=2
    and then lmdeploy returning INTERNAL_ENGINE_ERROR during two-step extract.
    Keep user-provided environment overrides intact; otherwise choose the more
    conservative defaults here.
    """
    normalized_backend = str(backend or "").strip().lower()
    if not normalized_backend.startswith("hybrid-"):
        return

    if not str(os.getenv("MINERU_HYBRID_BATCH_RATIO", "") or "").strip():
        os.environ["MINERU_HYBRID_BATCH_RATIO"] = "1"
    if not str(os.getenv("MINERU_PROCESSING_WINDOW_SIZE", "") or "").strip():
        os.environ["MINERU_PROCESSING_WINDOW_SIZE"] = "16"


def _slice_pdf_bytes(pdf_bytes: bytes, start_page_id: int = 0, end_page_id=None) -> bytes:
    """
    尽量按页截取 PDF。

    优先使用 MinerU 自带的 page slice helper；如果当前 mineru 版本不再提供该函数，
    则降级到 pymupdf 实现。两者都不可用时，直接返回原始 PDF，避免整条链路中断。
    """
    if pdf_bytes is None:
        return pdf_bytes

    if convert_pdf_bytes_to_bytes_by_pypdfium2 is not None:
        try:
            return convert_pdf_bytes_to_bytes_by_pypdfium2(pdf_bytes, start_page_id, end_page_id)
        except Exception as exc:
            logger.warning(f"MinerU page slice helper failed, fallback to pymupdf/raw PDF: {exc}")

    try:
        import fitz  # pymupdf

        src = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = src.page_count
        if total_pages <= 0:
            return pdf_bytes

        start = max(int(start_page_id or 0), 0)
        if end_page_id is None:
            end = total_pages - 1
        else:
            end = min(int(end_page_id), total_pages - 1)

        if start > end:
            return pdf_bytes

        if start == 0 and end == total_pages - 1:
            return pdf_bytes

        dst = fitz.open()
        dst.insert_pdf(src, from_page=start, to_page=end)
        return dst.tobytes()
    except Exception as exc:
        logger.warning(f"pymupdf page slice failed, using raw PDF bytes: {exc}")
        return pdf_bytes


def do_parse_md_only(
    output_dir,                  # Output directory for storing parsing results
    pdf_file_names: list[str],    # List of PDF file names to be parsed
    pdf_bytes_list: list[bytes],  # List of PDF bytes to be parsed
    p_lang_list: list[str],       # List of languages for each PDF
    backend="hybrid-auto-engine", # 'pipeline' / 'vlm-*' / 'hybrid-*'
    parse_method="ocr",          # 'auto' / 'txt' / 'ocr' (for pipeline/hybrid)
    formula_enable=True,
    table_enable=True,
    server_url=None,
    f_make_md_mode=MakeMode.MM_MD,
    start_page_id=0,
    end_page_id=None,
    **kwargs
):
    """
    只输出最终 md（以及 md 引用所必需的 images/）。
    不输出：_middle.json / _model.json / _content_list.json / _origin.pdf / bbox pdf
    """
    kwargs = _apply_default_lmdeploy_kwargs(backend, kwargs)
    _apply_default_mineru_runtime_env(backend)

    if backend == "pipeline":
        try:
            from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
            from mineru.backend.pipeline.pipeline_middle_json_mkcontent import union_make as pipeline_union_make
            from mineru.backend.pipeline.model_json_to_middle_json import (
                result_to_middle_json as pipeline_result_to_middle_json,
            )
        except ImportError as exc:
            raise RuntimeError(
                "当前 MinerU 版本缺少 pipeline 后端导入，无法执行 pipeline 模式。"
                "如果只是做 PDF -> MD，建议使用 hybrid-auto-engine。"
            ) from exc

        # pipeline：需要先按页截取
        for idx, pdf_bytes in enumerate(pdf_bytes_list):
            pdf_bytes_list[idx] = _slice_pdf_bytes(pdf_bytes, start_page_id, end_page_id)

        infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
            pdf_bytes_list,
            p_lang_list,
            parse_method=parse_method,
            formula_enable=formula_enable,
            table_enable=table_enable,
            **kwargs
        )

        for idx, model_list in enumerate(infer_results):
            pdf_file_name = pdf_file_names[idx]
            local_image_dir, local_md_dir = prepare_env(output_dir, pdf_file_name, parse_method)

            image_writer = FileBasedDataWriter(local_image_dir)
            md_writer = FileBasedDataWriter(local_md_dir)

            images_list = all_image_lists[idx]
            pdf_doc = all_pdf_docs[idx]
            _lang = lang_list[idx]
            _ocr_enable = ocr_enabled_list[idx]

            # pipeline 模型输出 -> middle_json
            middle_json = pipeline_result_to_middle_json(
                model_list, images_list, pdf_doc, image_writer, _lang, _ocr_enable, formula_enable
            )
            pdf_info = middle_json["pdf_info"]

            _write_md_only(
                pdf_info=pdf_info,
                pdf_file_name=pdf_file_name,
                local_image_dir=local_image_dir,
                md_writer=md_writer,
                f_make_md_mode=f_make_md_mode,
                is_pipeline=True,
            )

    else:
        # vlm/hybrid：span bbox 本来就禁用；我们也不输出 bbox/origin/json 等
        if backend.startswith("vlm-"):
            backend = backend[4:]
            if backend == "auto-engine":
                backend = get_vlm_engine(inference_engine="auto", is_async=False)

            parse_method = "vlm"
            for idx, pdf_bytes in enumerate(pdf_bytes_list):
                pdf_file_name = pdf_file_names[idx]
                pdf_bytes = _slice_pdf_bytes(pdf_bytes, start_page_id, end_page_id)

                local_image_dir, local_md_dir = prepare_env(output_dir, pdf_file_name, parse_method)
                image_writer = FileBasedDataWriter(local_image_dir)
                md_writer = FileBasedDataWriter(local_md_dir)

                middle_json, _infer_result = vlm_doc_analyze(
                    pdf_bytes, image_writer=image_writer, backend=backend, server_url=server_url, **kwargs
                )
                pdf_info = middle_json["pdf_info"]

                _write_md_only(
                    pdf_info=pdf_info,
                    pdf_file_name=pdf_file_name,
                    local_image_dir=local_image_dir,
                    md_writer=md_writer,
                    f_make_md_mode=f_make_md_mode,
                    is_pipeline=False,
                )

        elif backend.startswith("hybrid-"):
            backend = backend[7:]
            if backend == "auto-engine":
                backend = get_vlm_engine(inference_engine="auto", is_async=False)

            parse_method = f"hybrid_{parse_method}"
            for idx, pdf_bytes in enumerate(pdf_bytes_list):
                pdf_file_name = pdf_file_names[idx]
                pdf_bytes = _slice_pdf_bytes(pdf_bytes, start_page_id, end_page_id)

                local_image_dir, local_md_dir = prepare_env(output_dir, pdf_file_name, parse_method)
                image_writer = FileBasedDataWriter(local_image_dir)
                md_writer = FileBasedDataWriter(local_md_dir)

                middle_json, _infer_result, _vlm_ocr_enable = hybrid_doc_analyze(
                    pdf_bytes,
                    image_writer=image_writer,
                    backend=backend,
                    parse_method=parse_method,
                    language=p_lang_list[idx],
                    inline_formula_enable=formula_enable,
                    server_url=server_url,
                    **kwargs
                )
                pdf_info = middle_json["pdf_info"]

                _write_md_only(
                    pdf_info=pdf_info,
                    pdf_file_name=pdf_file_name,
                    local_image_dir=local_image_dir,
                    md_writer=md_writer,
                    f_make_md_mode=f_make_md_mode,
                    is_pipeline=False,
                )


def _write_md_only(
    pdf_info,
    pdf_file_name: str,
    local_image_dir: str,
    md_writer: FileBasedDataWriter,
    f_make_md_mode: MakeMode,
    is_pipeline: bool,
):
    """只写 md（保留 images/ 目录用于 md 引用）"""
    image_dir = str(os.path.basename(local_image_dir))
    make_func = pipeline_union_make if is_pipeline else vlm_union_make

    md_content_str = make_func(pdf_info, f_make_md_mode, image_dir)
    md_writer.write_string(f"{pdf_file_name}.md", md_content_str)

    logger.info(f"[MD-ONLY] local output dir is {md_writer.base_dir if hasattr(md_writer, 'base_dir') else 'N/A'}")


def parse_doc_md_only(
    path_list: list[Path],
    output_dir,
    lang="ch",
    backend="hybrid-auto-engine",
    method="auto",
    server_url=None,
    start_page_id=0,
    end_page_id=None,
    **kwargs
):
    try:
        kwargs = _apply_default_lmdeploy_kwargs(backend, kwargs)
        _apply_default_mineru_runtime_env(backend)
        file_name_list = []
        pdf_bytes_list = []
        lang_list = []

        for path in path_list:
            file_name = str(Path(path).stem)
            pdf_bytes = read_fn(path)
            file_name_list.append(file_name)
            pdf_bytes_list.append(pdf_bytes)
            lang_list.append(lang)

        do_parse_md_only(
            output_dir=output_dir,
            pdf_file_names=file_name_list,
            pdf_bytes_list=pdf_bytes_list,
            p_lang_list=lang_list,
            backend=backend,
            parse_method=method,
            server_url=server_url,
            start_page_id=start_page_id,
            end_page_id=end_page_id,
            **kwargs
        )
    except Exception as e:
        logger.exception(e)
        raise


if __name__ == "__main__":
    __dir__ = os.path.dirname(os.path.abspath(__file__))
    pdf_files_dir = os.path.join(__dir__, "pdfs")
    output_dir = os.path.join(__dir__, "output")

    pdf_suffixes = ["pdf"]
    image_suffixes = ["png", "jpeg", "jp2", "webp", "gif", "bmp", "jpg"]

    doc_path_list = []
    for doc_path in Path(pdf_files_dir).glob("*"):
        if guess_suffix_by_path(doc_path) in pdf_suffixes + image_suffixes:
            doc_path_list.append(doc_path)

    # 如果网络问题无法下载模型，可用 modelscope 源
    # os.environ["MINERU_MODEL_SOURCE"] = "modelscope"

    # ✅ 只输出 md（以及 images/）
    parse_doc_md_only(doc_path_list, output_dir, backend="hybrid-auto-engine")
    # 其他可选：
    # parse_doc_md_only(doc_path_list, output_dir, backend="pipeline")
    # parse_doc_md_only(doc_path_list, output_dir, backend="vlm-auto-engine")
    # parse_doc_md_only(doc_path_list, output_dir, backend="hybrid-http-client", server_url="http://127.0.0.1:30000")
