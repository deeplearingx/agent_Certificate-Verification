from pathlib import Path

from md_parser_no_llm import extract_meta_from_text, parse_md_to_json


class FakeMetaRepairLLM:
    def invoke_structured(self, user_prompt, output_model, system_prompt=None):
        slot_map = {}
        for raw_line in user_prompt.splitlines():
            line = raw_line.strip()
            if not line or ". " not in line:
                continue
            slot_text, value = line.split(". ", 1)
            if slot_text.isdigit():
                slot_map[value.strip()] = int(slot_text)
        return output_model(
            action="suggest",
            field_slots={
                "委托方地址": slot_map["广州市黄埔区长洲街海虹路63号"],
                "仪器名称": slot_map["机械秒表"],
                "型号规格": slot_map["803"],
                "制造商": slot_map["上海星钻秒表有限公司"],
                "机身号": slot_map["MB54"],
                "管理号": slot_map["/"],
                "接收日期": slot_map["2026-01-14"],
                "签发日期": slot_map["2026-01-19"],
            },
            confidence=0.97,
            reason="修复头部标签和值分离导致的串位",
        )


def _meta_for(md_name: str) -> dict:
    result = parse_md_to_json(str(Path("local_md") / md_name))
    return result["properties"]["证书列表"]["items"]["properties"]


def test_parse_md_to_json_recovers_header_fields_from_late_value_block():
    meta = _meta_for("2GB25026824-0010.md")

    assert meta["委托单位"] == "中国人民解放军92932部队（无线车间）"
    assert meta["仪器名称"] == "铷原子频率标准"
    assert meta["型号规格"] == "SYN3102型"
    assert meta["制造商"] == "西安同步电子"
    assert meta["机身号"] == "190403803"
    assert meta["管理号"] == "PLBZ075W"
    assert meta["接收日期"] == "2025-12-01"
    assert meta["校准日期"] == "2025-12-03"
    assert meta["签发日期"] == "2025-12-04"
    assert meta["建议校准周期"] == "12个月(12 months)"


def test_parse_md_to_json_recovers_bilingual_header_layout_fields():
    meta = _meta_for("2GB25025182-0012.md")

    assert meta["委托单位"] == "苏州UL美华认证有限公司广州分公司/UL-CCIC Company Limited,GuangZhou Branch"
    assert meta["委托方地址"].startswith("广州市黄埔区南云二路8号电子大楼B座101、201、301、401")
    assert "Room 101" in meta["委托方地址"]
    assert meta["仪器名称"] == "Counter"
    assert meta["型号规格"] == "/"
    assert meta["制造商"] == "CEPREI"
    assert meta["机身号"] == "SB110703"
    assert meta["管理号"] == "76580"
    assert meta["接收日期"] == "2025-11-13"
    assert meta["校准日期"] == "2025-11-24"


def test_extract_meta_from_text_splits_inline_cross_label_fields():
    text = "\n".join(
        [
            "证书编号：2GB25010404-0041",
            "委托单位： 元器件检测中心 委托方地址： 广东省广州市增城区朱村街朱村大道西78号",
            "仪器名称： 新体制RDSS及全球短报文信号源",
            "型号规格： RTS9000",
            "制造厂： 机身号： BD190K00000015330033",
            "机身号： BD190K00000015330033",
        ]
    )

    meta = extract_meta_from_text(text)

    assert meta["委托单位"] == "元器件检测中心"
    assert meta["委托方地址"] == "广东省广州市增城区朱村街朱村大道西78号"
    assert meta["仪器名称"] == "新体制RDSS及全球短报文信号源"
    assert meta.get("制造商", "") == ""
    assert meta["机身号"] == "BD190K00000015330033"


def test_parse_md_to_json_llm_repairs_suspicious_header_meta_layout():
    result = parse_md_to_json(
        str(Path("local_md") / "2GB26000944-0004.md"),
        llm_client=FakeMetaRepairLLM(),
    )

    meta = result["properties"]["证书列表"]["items"]["properties"]
    assert meta["委托方地址"] == "广州市黄埔区长洲街海虹路63号"
    assert meta["仪器名称"] == "机械秒表"
    assert meta["型号规格"] == "803"
    assert meta["制造商"] == "上海星钻秒表有限公司"
    assert meta["机身号"] == "MB54"
    assert meta.get("管理号", "") == ""
    assert meta["接收日期"] == "2026-01-14"
    assert meta["签发日期"] == "2026-01-19"

    parser_meta = result["__document_parser_meta"]
    assert parser_meta["meta_llm_fallback_applied"] is True
    assert parser_meta["meta_llm_fallback_reason"] == "修复头部标签和值分离导致的串位"
    assert set(parser_meta["meta_llm_fallback_slots"]) == {
        "委托方地址",
        "仪器名称",
        "型号规格",
        "制造商",
        "机身号",
        "接收日期",
        "签发日期",
    }
    assert parser_meta.get("meta_llm_fallback_cleared_fields", []) in ([], ["管理号"])


def test_parse_md_to_json_recovers_header_fields_from_label_block_with_late_values():
    meta = _meta_for("2GB25024401-0008.md")

    assert meta["委托单位"] == "深圳市万里眼技术有限公司"
    assert meta["委托方地址"] == "广东省深圳市龙岗区平湖街道平龙西路753号平湖智造园"
    assert meta["仪器名称"] == "微波频率计"
    assert meta["型号规格"] == "CNT-90XL-60G"
    assert meta["制造商"] == "pendulum"
    assert meta["机身号"] == "651340"
    assert meta["管理号"] == "F20241021000111"
    assert meta["接收日期"] == "2025-11-06"
    assert meta["校准日期"] == "2025-12-01"
    assert meta["签发日期"] == "2025-12-08"
    assert meta["建议校准周期"] == "12个月(12 months)"


def test_parse_md_to_json_recovers_inline_calibration_date_and_cycle_on_shared_line():
    meta = _meta_for("2GB25024388-0001.md")

    assert meta["接收日期"] == "2025-11-06"
    assert meta["校准日期"] == "2025-11-19"
    assert meta["签发日期"] == "2025-11-20"
    assert meta["建议校准周期"] == "12个月(12 months)"


def test_extract_meta_from_text_uses_header_scope_for_non_cnas_gnss_certificate():
    meta = _meta_for("2GB25013402-0009.md")

    assert meta.get("CNAS") is None
    assert meta.get("是否CNAS") is None


def test_extract_meta_from_text_preserves_cnas_when_header_has_cnas_mark():
    meta = _meta_for("2GB25021394-0003.md")

    assert meta.get("CNAS") == "是"
    assert meta.get("是否CNAS") == "是"
    assert meta.get("认可实验室") == "CNAS L13344"
    assert meta.get("CNAS编号") == "L13344"
