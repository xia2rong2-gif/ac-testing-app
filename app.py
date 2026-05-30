"""
伊莱克斯移动空调测试项目及方法查询 APP
"""
import streamlit as st
import pandas as pd
import os
from pathlib import Path

st.set_page_config(page_title="伊莱克斯移动空调测试查询", layout="wide", page_icon="❄️")

EXCEL_PATH = Path(__file__).parent / "伊莱克斯移动空调测试项目及方法.xlsx"


@st.cache_data
def load_master_sheet():
    """解析测试项目总纲,按"序号NO."行识别表头,提取类别、项目、标准。"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="测试项目总纲", header=None)
    # 找到表头行: 序号NO.
    header_idx = None
    for i, row in df.iterrows():
        for cell in row:
            if isinstance(cell, str) and "序号" in cell:
                header_idx = i
                break
        if header_idx is not None:
            break

    df.columns = df.iloc[header_idx].tolist()
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    # 提取前三列
    col_names = list(df.columns)
    cat_col = col_names[0]
    seq_col = col_names[1]
    item_col = col_names[2]
    std_col = col_names[3] if len(col_names) > 3 else None

    items = []
    current_cat = None
    for _, row in df.iterrows():
        cat = row[cat_col]
        seq = row[seq_col]
        item = row[item_col]
        std = row[std_col] if std_col else None
        if pd.notna(cat):
            current_cat = str(cat).strip()
        if pd.notna(seq) and pd.notna(item):
            try:
                seq_num = int(float(seq))
            except (ValueError, TypeError):
                continue
            std_str = str(std).strip() if pd.notna(std) else ""
            items.append({
                "类别": current_cat,
                "序号": seq_num,
                "测试项目": str(item).strip(),
                "测试标准": std_str
            })
    return items


@st.cache_data
def load_detail_sheet_test_method():
    """解析 测试方法 sheet: 序号+项目+判定要求+试验要求 + 多行合并"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="测试方法", header=None)
    header_idx = None
    for i, row in df.iterrows():
        for cell in row:
            if isinstance(cell, str) and "序号" in cell:
                header_idx = i
                break
        if header_idx is not None:
            break
    df.columns = df.iloc[header_idx].tolist()
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    col_names = list(df.columns)
    seq_col = col_names[0]
    item_col = col_names[1]
    judge_col = col_names[2]
    method_col = col_names[3]

    items = {}
    current_seq = None
    current_item = None
    current_judge_parts = []
    current_method_parts = []
    current_sub_lines = []

    SUB_LABELS = ["工况：", "布点：", "电源：", "装机要求：", "开机设置：",
                  "试验过程：", "实验步骤：", "试验方法：", "检查要求：",
                  "截图/照片输出：", "注意事项：", "实验方法："]

    def flush():
        if current_seq is not None and current_item:
            judge_text = "\n".join(current_judge_parts).strip()
            method_text = "\n".join(current_method_parts).strip()
            # Parse method_text into sub-sections
            parsed = {}
            current_label = None
            current_content = []
            for line in (method_text + "\n" + "\n".join(current_sub_lines)).split("\n"):
                line_stripped = line.strip()
                matched_label = None
                for lb in SUB_LABELS:
                    if line_stripped.startswith(lb):
                        matched_label = lb
                        break
                if matched_label:
                    if current_label and current_content:
                        parsed[current_label] = "\n".join(current_content).strip()
                    current_label = matched_label
                    rest = line_stripped[len(matched_label):]
                    current_content = [rest] if rest else []
                elif current_label:
                    current_content.append(line_stripped)
                else:
                    if "判级" not in line_stripped and line_stripped:
                        if current_judge_parts and len(current_judge_parts) < 20:
                            pass  # already in judge
            if current_label and current_content:
                parsed[current_label] = "\n".join(current_content).strip()

            if current_seq not in items:
                items[current_seq] = {
                    "序号": current_seq,
                    "项目": current_item,
                    "判定要求": judge_text,
                    **parsed
                }

        if "试验要求" in col_names:
            pass  # Extra cols

    for _, row in df.iterrows():
        seq = row[seq_col]
        item = row[item_col]
        judge = row[judge_col] if pd.notna(row[judge_col]) else ""
        method = row[method_col] if pd.notna(row[method_col]) else ""

        judge_s = str(judge).strip() if judge else ""
        method_s = str(method).strip() if method else ""

        if pd.notna(seq) and seq != "":
            try:
                new_seq = int(float(seq))
            except (ValueError, TypeError):
                new_seq = None
            if new_seq is not None and new_seq != current_seq:
                # Check rest of columns
                extra_cols = {}
                if len(col_names) > 4:
                    for ci in range(4, len(col_names)):
                        extra_cols[col_names[ci]] = row[col_names[ci]]
                flush()
                current_seq = new_seq
                current_item = str(item).strip() if pd.notna(item) and item != "" else None
                current_judge_parts = [judge_s] if judge_s else []
                current_method_parts = [method_s] if method_s else []
                current_sub_lines = [str(extra_cols.get(c, "")) for c in extra_cols if pd.notna(extra_cols.get(c))]
                continue

        if pd.notna(item) and str(item).strip() and current_seq is None:
            current_seq = 0
            current_item = str(item).strip()
            current_judge_parts = [judge_s] if judge_s else []
            current_method_parts = [method_s] if method_s else []
            continue

        if judge_s:
            current_judge_parts.append(judge_s)
        if method_s:
            current_method_parts.append(method_s)

    flush()
    return items


@st.cache_data
def load_safety_sheet():
    """解析 UL60335安规 sheet"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="UL60335安规", header=None)
    header_idx = None
    for i, row in df.iterrows():
        for cell in row:
            if isinstance(cell, str) and "序号" in cell:
                header_idx = i
                break
        if header_idx is not None:
            break
    if header_idx is None:
        return {}

    df.columns = df.iloc[header_idx].tolist()
    df = df.iloc[header_idx + 1:].reset_index(drop=True)
    col_names = list(df.columns)
    seq_col = col_names[0]
    item_col = col_names[1]
    judge_col = col_names[2] if len(col_names) > 2 else None
    method_col = col_names[3] if len(col_names) > 3 else None

    items = {}
    current_seq = None
    current_item = None
    parts_judge = []
    parts_method = []

    SUB_LABELS = ["工况：", "布点：", "电源：", "装机要求：", "开机设置：",
                  "试验过程：", "检查要求：", "截图/照片输出：", "注意事项："]

    def flush():
        if current_seq is not None and current_item:
            items[current_seq] = {
                "序号": current_seq,
                "项目": current_item,
                "判定要求": "\n".join(parts_judge).strip(),
            }
            # Parse method
            method_text = "\n".join(parts_method).strip()
            parsed = {}
            current_label = None
            current_content = []
            for line in method_text.split("\n"):
                ls = line.strip()
                matched = None
                for lb in SUB_LABELS:
                    if ls.startswith(lb):
                        matched = lb
                        break
                if matched:
                    if current_label and current_content:
                        parsed[current_label] = "\n".join(current_content).strip()
                    current_label = matched
                    rest = ls[len(matched):]
                    current_content = [rest] if rest else []
                elif current_label:
                    current_content.append(ls)
            if current_label and current_content:
                parsed[current_label] = "\n".join(current_content).strip()
            items[current_seq].update(parsed)

    for _, row in df.iterrows():
        seq = row[seq_col]
        item = row[item_col]
        judge = row[judge_col] if judge_col and pd.notna(row[judge_col]) else ""
        method = row[method_col] if method_col and pd.notna(row[method_col]) else ""
        judge_s = str(judge).strip() if judge else ""
        method_s = str(method).strip() if method else ""

        if pd.notna(seq):
            try:
                new_seq = int(float(seq))
            except (ValueError, TypeError):
                new_seq = None
            if new_seq is not None and new_seq != current_seq:
                flush()
                current_seq = new_seq
                current_item = str(item).strip() if pd.notna(item) else ""
                parts_judge = [judge_s] if judge_s else []
                parts_method = [method_s] if method_s else []
                continue

        if judge_s:
            parts_judge.append(judge_s)
        if method_s:
            parts_method.append(method_s)

    flush()
    return items


@st.cache_data
def load_electrical_sheet():
    """解析 电控测试项目 sheet"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="电控测试项目", header=None)
    # Find header row with 试验项目
    header_idx = None
    for i, row in df.iterrows():
        found = False
        for cell in row:
            if isinstance(cell, str) and "试验项目" in cell:
                header_idx = i
                found = True
                break
        if found:
            break
    if header_idx is None:
        return {}

    df.columns = df.iloc[header_idx].tolist()
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    # Remove unnamed/NaN columns
    df = df.loc[:, ~df.columns.astype(str).str.contains("Unnamed", na=False)]

    col_names = list(df.columns)
    items = {}
    current_seq = None
    current_item = None
    parts = {}

    seq_col = col_names[0] if col_names[0] != "类别" else col_names[1]

    SUB_LABELS = ["测试标准", "试验要求", "判定要求", "验证机型及数量"]
    text_cols = [c for c in col_names if c in SUB_LABELS]

    for _, row in df.iterrows():
        seq = None
        for c in col_names:
            v = row[c]
            if pd.notna(v):
                try:
                    seq = int(float(v))
                    break
                except (ValueError, TypeError):
                    pass

        item = None
        for c in col_names:
            if isinstance(row[c], str) and len(row[c]) > 2 and seq is not None:
                # check if it doesn't start with 测试/电源/截图/注意事项
                val = str(row[c]).strip()
                if not any(val.startswith(p) for p in SUB_LABELS):
                    item = val
                    break

        if seq is not None and seq != current_seq:
            if current_seq is not None:
                items[current_seq] = {"序号": current_seq, "项目": current_item}
                for c in text_cols:
                    parts.setdefault(c, [])
                    items[current_seq][c] = "\n".join(parts[c]).strip()
            current_seq = seq
            current_item = item
            parts = {}
            for c in text_cols:
                parts[c] = []
        elif seq is None and current_seq is not None:
            for c in text_cols:
                if pd.notna(row[c]):
                    parts.setdefault(c, [])
                    parts[c].append(str(row[c]).strip())

    if current_seq is not None:
        items[current_seq] = {"序号": current_seq, "项目": current_item}
        for c in text_cols:
            parts.setdefault(c, [])
            items[current_seq][c] = "\n".join(parts[c]).strip()

    return items


@st.cache_data
def load_wifi_sheet():
    """解析 Wifi connectivity test sheet"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="Wifi connectivity test", header=None)
    df.columns = df.iloc[1].tolist()
    df = df.iloc[2:].reset_index(drop=True)
    # find 序号 column
    col_names = list(df.columns)
    seq_col = None
    for c in col_names:
        if isinstance(c, str) and ("序号" in c or "Unnamed" not in c):
            seq_col = c
            break

    items = {}
    for _, row in df.iterrows():
        seq = row.iloc[0]
        if pd.notna(seq):
            try:
                seq_num = int(float(seq))
            except (ValueError, TypeError):
                continue
            item_data = {}
            for i, c in enumerate(col_names):
                if i < len(row) and pd.notna(row.iloc[i]):
                    item_data[str(c)] = str(row.iloc[i]).strip()
            items[seq_num] = item_data
    return items


@st.cache_data
def load_longrun_sheet():
    """解析 长期运行 sheet"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="长期运行", header=None)
    header_idx = None
    for i, row in df.iterrows():
        for cell in row:
            if isinstance(cell, str) and "序号" in cell:
                header_idx = i
                break
        if header_idx is not None:
            break

    df.columns = df.iloc[header_idx].tolist()
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    col_names = list(df.columns)
    seq_col = col_names[1]
    item_col = col_names[2]
    judge_col = col_names[3] if len(col_names) > 3 else None
    method_col = col_names[4] if len(col_names) > 4 else None

    items = {}
    for _, row in df.iterrows():
        seq = row[seq_col]
        if pd.notna(seq):
            try:
                seq_num = int(float(seq))
            except (ValueError, TypeError):
                continue
            item_name = str(row[item_col]).strip() if pd.notna(row[item_col]) else ""
            judge = str(row[judge_col]).strip() if judge_col and pd.notna(row[judge_col]) else ""
            method = str(row[method_col]).strip() if method_col and pd.notna(row[method_col]) else ""
            items[seq_num] = {
                "序号": seq_num,
                "项目": item_name,
                "判定要求": judge,
                "试验要求": method
            }
    return items


@st.cache_data
def load_ptc_sheet():
    """解析 PTC 电加热测试 sheet"""
    df = pd.read_excel(EXCEL_PATH, sheet_name="PTC 电加热测试", header=None)
    col_names = list(df.columns)

    items = {}
    current_item = None
    parts = []
    SUB_LABELS = ["工况：", "布点：", "电源：", "装机要求：", "开机设置：",
                  "试验过程：", "检查要求：", "截图/照片输出：", "注意事项："]

    def flush_item():
        if current_item:
            method_text = "\n".join(parts).strip()
            parsed = {}
            current_label = None
            current_content = []
            judge_text = ""
            for line in method_text.split("\n"):
                ls = line.strip()
                matched = None
                for lb in SUB_LABELS:
                    if ls.startswith(lb):
                        matched = lb
                        break
                if matched:
                    if current_label and current_content:
                        parsed[current_label] = "\n".join(current_content).strip()
                    current_label = matched
                    rest = ls[len(matched):]
                    current_content = [rest] if rest else []
                elif current_label:
                    current_content.append(ls)
                elif not current_label and ls and "判级" not in ls:
                    judge_text += ls + "\n"
            if current_label and current_content:
                parsed[current_label] = "\n".join(current_content).strip()
            idx = len(items) + 1
            items[idx] = {"序号": idx, "项目": current_item, "判定要求": judge_text.strip(), **parsed}
            parts.clear()

    for _, row in df.iterrows():
        cell0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        cell1 = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""

        if cell0 and not any(cell0.startswith(lb) for lb in SUB_LABELS) and len(cell0) > 3:
            if "试验" in cell0 or "测试" in cell0:
                flush_item()
                current_item = cell0
                continue
        if current_item:
            for i, c in enumerate(row):
                if pd.notna(c):
                    parts.append(str(c).strip())

    flush_item()
    return items


def build_detailed_lookup():
    """合并所有详细数据为一个 lookup dict"""
    lookup = {}
    for d in [load_detail_sheet_test_method(), load_safety_sheet(),
              load_electrical_sheet(), load_wifi_sheet(),
              load_longrun_sheet(), load_ptc_sheet()]:
        for k, v in d.items():
            lookup[k] = v
    return lookup


def display_item_detail(item_data: dict, detail_lookup: dict):
    """根据序号查找并展示详细内容"""
    seq = item_data["序号"]
    detail = detail_lookup.get(seq, {})
    std = item_data.get("测试标准", "")

    cols = st.columns([1, 3])
    with cols[0]:
        st.markdown(f"**序号:** {seq}")
        if std:
            st.markdown(f"**测试标准:** {std}")
    with cols[1]:
        st.markdown(f"**测试项目:** {item_data['测试项目']}")

    st.divider()

    if not detail:
        st.info("暂无详细测试方法数据")
        return

    # Display judgment criteria
    judge = detail.get("判定要求", "")
    if judge:
        with st.expander("判定要求", expanded=True):
            st.text(judge)

    # Display test method sections
    section_labels = {
        "工况：": "测试工况",
        "布点：": "布点要求",
        "电源：": "电源要求",
        "装机要求：": "装机要求",
        "开机设置：": "开机设置",
        "试验过程：": "试验过程",
        "实验步骤：": "实验步骤",
        "试验方法：": "试验方法",
        "检查要求：": "检查要求",
        "截图/照片输出：": "截图/照片输出",
        "注意事项：": "注意事项",
        "试验要求": "试验要求",
        "测试标准": "测试标准",
        "验证机型及数量": "验证机型及数量",
    }

    shown = False
    for label_key, display_name in section_labels.items():
        content = detail.get(label_key, "")
        if content:
            with st.expander(display_name, expanded=(label_key in ["工况：", "试验过程：", "检查要求："])):
                st.text(content)
            shown = True

    # Show extra fields
    for k, v in detail.items():
        if k not in ["序号", "项目", "判定要求"] and k not in section_labels:
            if v:
                with st.expander(k):
                    st.text(v)
                shown = True

    if not shown:
        # Show everything
        for k, v in detail.items():
            if k not in ["序号", "项目"] and v:
                with st.expander(k):
                    st.text(v)


# ===== Main App =====
def main():
    st.title("❄️ 伊莱克斯移动空调测试项目及方法查询")

    items = load_master_sheet()
    detail_lookup = build_detailed_lookup()

    # Get unique categories
    categories = sorted(set(it["类别"] for it in items if it["类别"]))

    with st.sidebar:
        st.header("选择测试类别")
        sel_category = st.selectbox("测试类别", categories)
        st.divider()
        st.markdown("**测试项目列表**")
        st.caption(f"共 {len(items)} 项测试")

        # Filter items by category
        cat_items = [it for it in items if it["类别"] == sel_category]
        sel_option = st.radio(
            "点击项目查看详情",
            options=[f"{it['序号']}. {it['测试项目']}" for it in cat_items],
            label_visibility="collapsed",
            index=0
        )
        if sel_option:
            sel_seq = int(sel_option.split(".")[0])
            sel_item = next((it for it in cat_items if it["序号"] == sel_seq), cat_items[0])

    # Main content
    if sel_item:
        st.subheader(f"{sel_item['序号']}. {sel_item['测试项目']}")
        display_item_detail(sel_item, detail_lookup)

    # Footer
    st.divider()
    st.caption(f"数据来源: {EXCEL_PATH.name}")


if __name__ == "__main__":
    main()
