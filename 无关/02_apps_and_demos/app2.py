import streamlit as st
import os
import time
from pathlib import Path
import threading
from sentence_transformers import SentenceTransformer
import tempfile
import shutil

# === 导入你的自定义模块 ===
import md_parser
import info_check
import env_check
import cycle_check
import param_check
import location_check




# ✅ 导入 pdf_md.py（你给的那个文件）
import pdf_md
DEFAULT_API_KEY = os.getenv("API_KEY", "")

# ===================== 默认配置类 (作为初始值) =====================
class DefaultConfig:
    DB_DIR = r"./vector_db/cnas_calibration"
    TEMP_DB_DIR = "./vector_db/temperature"
    GENERAL_DB_DIR = "./vector_db/general_cycle"
    HUAWEI_DB_DIR = "./vector_db/huawei_cycle"
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"

    USE_LLM_VERIFICATION = True
    COLLECTION = "calibration_data"
    DEFAULT_CYCLE = "12个月"

    API_BASE = "https://api.deepseek.com/v1"
    MODEL = "deepseek-chat"
    TEMPERATURE = 0.1
    MAX_TOKENS = 2048
    TOPK = 50
    BATCH_SIZE = 5

    ADDR_DB_DIR = r"./vector_db/address"
    ADDR_COLLECTION = "calibration_address"
    MUST_MATCH_THRESHOLD = 0.45
    OPTIONAL_MATCH_THRESHOLD = 0.45

    USE_LLM_LOCATION_CHECK = True
    LLM_TEMPERATURE = 0.0
    LLM_MAX_TOKENS = 256


# ===================== 页面设置 =====================
st.set_page_config(
    page_title="智能文档核验系统",
    page_icon="📑",
    layout="wide"
)

# ===================== 路径全局配置 =====================
CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR

BASE_PDF_DIR = BASE_DIR / "local_pdf"
BASE_MD_DIR = BASE_DIR / "local_md"
BASE_JSON_DIR = BASE_DIR / "local_json"
OUTPUT_DIR = BASE_DIR / "final_reports"

for p in [BASE_PDF_DIR, BASE_MD_DIR, BASE_JSON_DIR, OUTPUT_DIR]:
    p.mkdir(parents=True, exist_ok=True)


def find_and_copy_md(tmp_out_dir: Path, stem: str, dst_md_dir: Path) -> Path | None:
    """
    pdf_md.parse_doc_md_only 会在 output_dir 下生成一层目录结构（prepare_env）。
    我们递归找 {stem}.md，然后复制到 local_md 根目录，供 md_parser 使用。
    """
    md_candidates = list(tmp_out_dir.rglob(f"{stem}.md"))
    if not md_candidates:
        return None
    src = md_candidates[0]
    dst = dst_md_dir / f"{stem}.md"
    shutil.copyfile(src, dst)
    return dst


def pdf_to_md_first_step(
    pdf_path: Path,
    status_text,
    progress_bar,
    stop_event,
    backend="hybrid-auto-engine",
    method="auto",
    lang="ch",
):
    """
    ✅ 第一步：PDF -> MD（带缓存）
    - 如果 local_md 里已经有同名 md：直接复用
    - 否则调用 pdf_md.py 解析生成
    """
    if stop_event.is_set():
        return None

    stem = pdf_path.stem
    cached_md = BASE_MD_DIR / f"{stem}.md"

    # ✅ 缓存命中：直接用
    if cached_md.exists() and cached_md.stat().st_size > 0:
        status_text.text("Processing [0/7]: PDF → MD（缓存命中）直接使用现有 MD ✅")
        progress_bar.progress(10)
        st.info(f"⏩ [缓存命中] 已存在 MD：{cached_md.name}，跳过 PDF 解析")
        return cached_md

    # 否则开始解析
    status_text.text("Processing [0/7]: PDF → MD（MinerU）准备中…")
    progress_bar.progress(3)

    with tempfile.TemporaryDirectory() as tmp_out:
        tmp_out_dir = Path(tmp_out)

        status_text.text("Processing [0/7]: PDF → MD（MinerU）解析中（较耗时）…")
        progress_bar.progress(6)

        pdf_md.parse_doc_md_only(
            path_list=[pdf_path],
            output_dir=str(tmp_out_dir),
            lang=lang,
            backend=backend,
            method=method,
            server_url=None,
            start_page_id=0,
            end_page_id=None,
            batch_size=1  # 设置为 1，避免 CUDA 内存不足
        )

        if stop_event.is_set():
            return None

        status_text.text("Processing [0/7]: PDF → MD（MinerU）整理输出…")
        progress_bar.progress(9)

        md_path = find_and_copy_md(tmp_out_dir, stem, BASE_MD_DIR)
        if not md_path:
            return None

        status_text.text("Processing [0/7]: PDF → MD（MinerU）完成 ✅")
        progress_bar.progress(10)
        return md_path



# ===================== 核心逻辑封装 =====================
def run_verification(pdf_file_path, user_config, progress_bar, status_text, stop_event):
    """
    执行核验流程：PDF -> MD -> JSON -> 校验
    """
    full_report = [
        f"# 🏆 全流程智能核验报告",
        f"**源文件**：`{pdf_file_path.name}`",
        f"**核验时间**：`{time.strftime('%Y-%m-%d %H:%M:%S')}`",
        f"**核验模型**：`{user_config.MODEL}` (Temp: {user_config.TEMPERATURE}, TopK: {user_config.TOPK})",
        "---"
    ]

    os.environ["DEEPSEEK_API_KEY"] = user_config.API_KEY

    # 🛑 检查点
    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 0️⃣ 第一步：PDF -> MD（MinerU）
    # ---------------------------------------------------------
    md_path = pdf_to_md_first_step(
        pdf_path=pdf_file_path,
        status_text=status_text,
        progress_bar=progress_bar,
        stop_event=stop_event,
        backend="hybrid-auto-engine",
        method="ocr",
        lang="ch",
    )

    if stop_event.is_set():
        return "⚠️ 任务已终止 (PDF→MD 阶段)"

    if not md_path or not md_path.exists():
        st.error("🛑 PDF → MD 解析失败：未生成 MD")
        return None

    full_report.append(f"## ✅ PDF → MD 解析成功\n> 生成 MD：`{md_path.name}`\n")

    # ---------------------------------------------------------
    # 📥 提前加载 embedding（供 param_check/location_check 复用）
    # ---------------------------------------------------------
    status_text.text("正在准备 AI 模型资源...")
    shared_embedder = load_global_model(user_config.EMBED_MODEL_PATH)

    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 1️⃣ 模块一：MD 解析（MD -> JSON）
    # ---------------------------------------------------------
    status_text.text("Processing [1/6]: MD 解析与数据提取...")
    progress_bar.progress(10)

    expected_json_name = md_path.with_suffix(".json").name
    json_path = BASE_JSON_DIR / expected_json_name

    if json_path.exists():
        st.info(f"⏩ [缓存命中] 直接使用现有 JSON: {expected_json_name}")
        full_report.append(
            f"## ✅ MD 解析 (跳过)\n> 检测到现有 JSON 文件 `{expected_json_name}`，直接使用。\n"
        )
    else:
        try:
            generated_path = md_parser.run_md_parsing(
                md_filename=md_path.name,
                base_dir=BASE_MD_DIR,
                out_dir=BASE_JSON_DIR,
                api_key=user_config.API_KEY,
                stop_event=stop_event,
                api_base=user_config.API_BASE,
                model=user_config.MODEL,
                max_workers=getattr(user_config, "max_workers", 5),
            )

            if stop_event.is_set():
                return "⚠️ 任务已终止 (MD解析阶段)"

            if not generated_path:
                raise Exception("MD 解析未生成有效的 JSON 文件")

            json_path = Path(generated_path)
            full_report.append(f"## ✅ MD 解析成功\n> JSON文件已生成：`{json_path.name}`\n")
        except Exception as e:
            st.error(f"🛑 MD 解析失败: {e}")
            return None

    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 2️⃣ 模块二：完整性与资格核验
    # ---------------------------------------------------------
    status_text.text("Processing [2/6]: 信息完整性核验...")
    progress_bar.progress(30)
    try:
        report_1 = info_check.check_certificate_integrity(str(json_path))
        if "核验终止报告" in report_1 or "系统拒绝处理" in report_1:
            st.error("🛑 证书不符合 CNAS 要求或严重缺失，流程终止。")
            full_report.append(report_1)
            return "\n".join(full_report)

        full_report.append(report_1)
        st.success("✅ 完整性核验完成")
    except Exception as e:
        st.error(f"❌ 完整性核验异常: {e}")
        full_report.append(f"## ❌ 完整性核验异常\n> Error: {str(e)}\n")

    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 3️⃣ 模块三：环境条件核验
    # ---------------------------------------------------------
    status_text.text("Processing [3/6]: 环境条件核验...")
    progress_bar.progress(50)
    try:
        report_2 = env_check.check_environment(str(json_path), user_config)
        full_report.append("\n---\n" + report_2)
    except Exception as e:
        st.warning(f"⚠️ 环境核验异常: {e}")
        full_report.append(f"## ❌ 环境核验异常\n> Error: {str(e)}\n")

    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 4️⃣ 模块四：校准地点核验
    # ---------------------------------------------------------
    status_text.text("Processing [4/6]: 校准地点核验...")
    progress_bar.progress(65)
    try:
        report_loc = location_check.check_location(
            json_file=str(json_path),
            cfg=user_config,
            embedder_obj=shared_embedder,
            stop_event=stop_event
        )
        full_report.append("\n---\n" + report_loc)
        st.success("✅ 校准地点核验完成")
    except Exception as e:
        st.warning(f"⚠️ 校准地点核验异常: {e}")
        full_report.append(f"## ❌ 校准地点核验异常\n> Error: {str(e)}\n")

    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 5️⃣ 模块五：校准周期核验
    # ---------------------------------------------------------
    status_text.text("Processing [5/6]: 校准周期核验...")
    progress_bar.progress(70)
    try:
        try:
            report_3 = cycle_check.check_cycle_reasonableness(str(json_path), user_config, stop_event=stop_event)
        except TypeError:
            report_3 = cycle_check.check_cycle_reasonableness(str(json_path), user_config)

        full_report.append("\n---\n" + report_3)
    except Exception as e:
        st.warning(f"⚠️ 周期核验异常: {e}")
        full_report.append(f"## ❌ 周期核验异常\n> Error: {str(e)}\n")

    if stop_event.is_set():
        return "⚠️ 任务已终止"

    # ---------------------------------------------------------
    # 6️⃣ 模块六：参数与不确定度核验 (最耗时)
    # ---------------------------------------------------------
    status_text.text("Processing [6/6]: 依据与参数核验 (DeepSeek 深度思考中)...")
    progress_bar.progress(90)
    try:
        report_4 = param_check.run_llm_mode(
            str(json_path),
            user_config,
            stop_event=stop_event,
            embedder_obj=shared_embedder
        )

        if stop_event.is_set():
            return "⚠️ 任务已终止 (参数核验阶段)"

        full_report.append("\n---\n" + report_4)
    except Exception as e:
        st.error(f"❌ 参数核验异常: {e}")
        full_report.append(f"## ❌ 参数核验异常\n> Error: {str(e)}\n")

    progress_bar.progress(100)
    status_text.text("🎉 全部流程执行完毕")
    return "\n".join(full_report)


@st.cache_resource
def load_global_model(model_path):
    print(f"🔥 [System] 首次加载共享模型: {model_path}")
    return SentenceTransformer(model_path)


# ===================== 主界面逻辑 =====================
def main():
    st.title("📑 AI 智能文档核验系统")
    st.markdown("通过多智能体协作，对 **PDF 证书**进行全流程自动化核验（PDF → MD → JSON → 校验）。")

    if 'running' not in st.session_state:
        st.session_state.running = False

    if 'stop_event' not in st.session_state:
        st.session_state.stop_event = threading.Event()

    # ===================== 侧边栏配置 =====================
    with st.sidebar:
        st.header("⚙️ 系统配置")
        api_key_input = st.text_input(
            "DeepSeek API Key",
            value=DEFAULT_API_KEY,
            type="password"
        )
        st.divider()

        with st.expander("🧠 LLM 模型参数", expanded=True):
            temperature = st.slider("Temperature", 0.0, 1.0, DefaultConfig.TEMPERATURE, 0.1)
            max_tokens = st.number_input("Max Tokens", 512, 8192, DefaultConfig.MAX_TOKENS, 256)
            top_k = st.number_input("Top K", 1, 100, DefaultConfig.TOPK)
            model_name = st.selectbox("Model", ["deepseek-chat", "deepseek-coder"], index=0)

        with st.expander("📊 周期核验参数", expanded=False):
            default_cycle = st.text_input("默认校准周期", value=DefaultConfig.DEFAULT_CYCLE)
            use_llm_verify = st.checkbox("启用 LLM 完整性核验增强", value=DefaultConfig.USE_LLM_VERIFICATION)

        with st.expander("📂 系统路径配置 (高级)", expanded=False):
            st.markdown("### 🧲 核心模型与库")
            embed_model = st.text_input("Embedding Model Path", value=DefaultConfig.EMBED_MODEL_PATH)
            db_dir = st.text_input("Main Vector DB (CNAS)", value=DefaultConfig.DB_DIR)

            st.markdown("### 🌡️ 辅助数据库")
            temp_db_dir = st.text_input("Temperature DB", value=DefaultConfig.TEMP_DB_DIR)
            general_db_dir = st.text_input("General Cycle DB", value=DefaultConfig.GENERAL_DB_DIR)
            huawei_db_dir = st.text_input("Huawei Cycle DB", value=DefaultConfig.HUAWEI_DB_DIR)
            st.caption("注：路径建议使用绝对路径。")

        with st.expander("📍 校准地点核验参数", expanded=False):
            addr_db_dir = st.text_input("Address DB Dir", value=DefaultConfig.ADDR_DB_DIR)
            addr_collection = st.text_input("Address Collection", value=DefaultConfig.ADDR_COLLECTION)
            must_thr = st.number_input("MUST_MATCH_THRESHOLD", 0.0, 1.0, DefaultConfig.MUST_MATCH_THRESHOLD, 0.01)
            opt_thr = st.number_input("OPTIONAL_MATCH_THRESHOLD", 0.0, 1.0, DefaultConfig.OPTIONAL_MATCH_THRESHOLD, 0.01)
            use_llm_loc = st.checkbox("启用 LLM 地点具体性判定", value=DefaultConfig.USE_LLM_LOCATION_CHECK)

        st.markdown("---")
        st.markdown("Developed by AI Team")

    # ===================== 构建 Config =====================
    class DynamicConfig:
        pass

    current_config = DynamicConfig()
    current_config.API_KEY = api_key_input
    current_config.TEMPERATURE = temperature
    current_config.MAX_TOKENS = max_tokens
    current_config.TOPK = top_k
    current_config.MODEL = model_name
    current_config.DEFAULT_CYCLE = default_cycle
    current_config.USE_LLM_VERIFICATION = use_llm_verify
    current_config.DB_DIR = db_dir
    current_config.EMBED_MODEL_PATH = embed_model
    current_config.TEMP_DB_DIR = temp_db_dir
    current_config.GENERAL_DB_DIR = general_db_dir
    current_config.HUAWEI_DB_DIR = huawei_db_dir
    current_config.API_BASE = DefaultConfig.API_BASE
    current_config.COLLECTION = DefaultConfig.COLLECTION
    current_config.BATCH_SIZE = DefaultConfig.BATCH_SIZE
    current_config.max_workers = 5

    current_config.CNAS_DB_DIR = current_config.DB_DIR
    current_config.CNAS_COLLECTION = current_config.COLLECTION

    current_config.ADDR_DB_DIR = addr_db_dir
    current_config.ADDR_COLLECTION = addr_collection
    current_config.MUST_MATCH_THRESHOLD = must_thr
    current_config.OPTIONAL_MATCH_THRESHOLD = opt_thr
    current_config.USE_LLM_LOCATION_CHECK = use_llm_loc

    # ===================== 主区域：上传 PDF =====================
    uploaded_file = st.file_uploader("请上传待核验的 **PDF 文件**", type=["pdf"])

    if uploaded_file:
        col_info1, col_info2 = st.columns([3, 1])
        with col_info1:
            st.write(f"📄 文件名: **{uploaded_file.name}**")
        with col_info2:
            st.write(f"📦 大小: {uploaded_file.size / 1024:.2f} KB")

        st.divider()

        button_placeholder = st.empty()

        if st.session_state.running:
            if button_placeholder.button("🛑 正在核验中... 点击终止", type="primary"):
                st.session_state.stop_event.set()
                st.session_state.running = False
                st.rerun()
        else:
            if button_placeholder.button("🚀 开始智能核验"):
                if not api_key_input:
                    st.error("❌ 请先在左侧配置 API Key")
                else:
                    st.session_state.stop_event.clear()
                    st.session_state.running = True
                    st.rerun()

        if st.session_state.running:
            target_pdf_path = BASE_PDF_DIR / uploaded_file.name
            with open(target_pdf_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            result_container = st.container()
            progress_bar = result_container.progress(0)
            status_text = result_container.empty()

            try:
                final_report = run_verification(
                    target_pdf_path,
                    current_config,
                    progress_bar,
                    status_text,
                    st.session_state.stop_event
                )

                if final_report:
                    st.success("✅ 核验完成！")
                    st.session_state['last_report'] = final_report

                    try:
                        save_path = OUTPUT_DIR / f"Report_{target_pdf_path.stem}.md"
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(final_report)
                        st.caption(f"💾 服务器备份路径: {save_path}")
                    except Exception as e:
                        st.error(f"❌ 本地保存失败: {e}")

                    st.download_button(
                        label="📥 下载完整 Markdown 报告 (推荐)",
                        data=final_report,
                        file_name=f"Report_{target_pdf_path.stem}.md",
                        mime="text/markdown",
                        type="primary"
                    )

                    MAX_PREVIEW_LENGTH = 10000
                    with st.expander("📝 核验报告预览 (点击展开)", expanded=True):
                        if len(final_report) > MAX_PREVIEW_LENGTH:
                            st.warning(
                                f"⚠️ 报告内容过长 ({len(final_report)} 字符)，为防止浏览器卡死，仅显示前 {MAX_PREVIEW_LENGTH} 字符。请下载完整版。"
                            )
                            st.markdown(final_report[:MAX_PREVIEW_LENGTH] + "\n\n...(内容过长已截断，请下载完整版)...")
                        else:
                            st.markdown(final_report)

            except Exception as e:
                st.error(f"❌ 发生错误: {e}")

            finally:
                st.session_state.running = False
                button_placeholder.empty()
                if button_placeholder.button("🚀 开始智能核验", key="restart_btn"):
                    st.session_state.stop_event.clear()
                    st.session_state.running = True
                    st.rerun()

    if not st.session_state.running and 'last_report' in st.session_state:
        st.info("💡 上次核验结果已保留：")
        with st.expander("📝 历史报告", expanded=False):
            st.markdown(st.session_state['last_report'])


if __name__ == "__main__":
    main()
