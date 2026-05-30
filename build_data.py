"""
Build multi-product JSON data for PWA
Products: 伊莱克斯移动空调, 伊莱克斯除湿机
"""
import pandas as pd
import json

OUTPUT = "app_data.json"

# Product configs: (file, name, seq_offset)
PRODUCTS = [
    ("伊莱克斯移动空调测试项目及方法.xlsx", "移动空调", 0),
    ("伊莱克斯除湿机测试项目及方法_V3 (1).xlsm", "除湿机", 300),
]

SUB_LABELS = ["工况：", "布点：", "电源：", "装机要求：", "开机设置：",
              "试验过程：", "试验方法：", "实验方法：", "实验步骤：",
              "检查要求：", "截图/照片输出：", "注意事项：", "测试标准："]

# ── Helpers ──

def clean_detail(detail):
    cleaned = {}
    for k, v in detail.items():
        if not v: continue
        k = str(k).strip()
        if k.lower() in ("nan", "none", "", "unnamed"): continue
        if k.startswith("Unnamed") or k.startswith("col"): continue
        cleaned[k] = v
    return cleaned


def split_combined(detail):
    """Split keys like 试验要求 into sub-sections."""
    result = dict(detail)
    for key in ["试验要求", "details", "全部内容"]:
        text = result.get(key, "")
        if not text: continue
        parsed = {}
        label = None
        content = []
        for line in text.split("\n"):
            ls = line.strip()
            matched = None
            for lb in SUB_LABELS:
                if ls.startswith(lb): matched = lb; break
            if matched:
                if label and content: parsed[label] = "\n".join(content).strip()
                label = matched
                content = [ls[len(matched):]] if ls[len(matched):] else []
            elif label:
                content.append(ls)
        if label and content: parsed[label] = "\n".join(content).strip()
        if parsed:
            result.pop(key, None)
            result.update(parsed)
    return result


def find_header_row(df, keywords):
    for i, row in df.iterrows():
        row_text = " ".join(str(c) for c in row if isinstance(c, str))
        if all(kw in row_text for kw in keywords):
            return i
    return 0


# ── Parsers ──

def parse_master(xl, product, offset):
    """Parse 测试项目汇总 / 测试项目总纲 → master items"""
    sheet = None
    for s in xl.sheet_names:
        if "项目汇总" in s or "项目总纲" in s:
            sheet = s; break
    if not sheet: return [], {}, {}

    df = pd.read_excel(xl, sheet_name=sheet, header=None)
    hi = find_header_row(df, ["类别", "序号", "项目"])
    df.columns = df.iloc[hi].tolist()
    df = df.iloc[hi+1:].reset_index(drop=True)
    cols = list(df.columns)
    cat_idx = 0
    # Find seq and item column indices
    seq_idx = 1; item_idx = 2; std_idx = 3 if len(cols) > 3 else None
    for i, c in enumerate(cols):
        s = str(c).strip()
        if "序号" in s or "NO" in s.upper(): seq_idx = i
        if s in ("项目", "测试项目"): item_idx = i

    items = []
    current_cat = None
    for _, r in df.iterrows():
        if pd.notna(r.iloc[cat_idx]): current_cat = str(r.iloc[cat_idx]).strip()
        seq = r.iloc[seq_idx]; item = r.iloc[item_idx]
        if pd.notna(seq) and pd.notna(item):
            try: seq_num = int(float(seq))
            except: continue
            std = str(r.iloc[std_idx]).strip() if std_idx is not None and pd.notna(r.iloc[std_idx]) else ""
            items.append({"cat": current_cat, "seq": seq_num + offset, "item": str(item).strip(), "std": std, "product": product})

    cats = sorted(set(it["cat"] for it in items if it["cat"]))
    cat_items = {}
    for it in items:
        cat_items.setdefault(it["cat"], []).append(it)
    return cats, cat_items, items


def parse_detail_sheet(xl, sheet_name, seq_offset=0, seq_col_idx=0, item_col_idx=1, data_start_col=2):
    """Generic parser for detail sheets with continuation rows."""
    if sheet_name not in xl.sheet_names: return {}
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    hi = find_header_row(df, ["序号", "项目"])
    df.columns = df.iloc[hi].tolist()
    df = df.iloc[hi+1:].reset_index(drop=True)
    col_names = list(df.columns)

    result = {}
    cur_seq = None; cur_item = None; cur_detail = {}
    for _, r in df.iterrows():
        first = r.iloc[seq_col_idx]
        if pd.notna(first):
            try: ns = int(float(first))
            except: ns = None
            if ns is not None and ns != cur_seq:
                if cur_seq is not None and cur_item:
                    result[cur_seq + seq_offset] = {"seq": cur_seq + seq_offset, "item": cur_item, "detail": dict(cur_detail)}
                cur_seq = ns; cur_item = str(r.iloc[item_col_idx]).strip() if pd.notna(r.iloc[item_col_idx]) else ""
                cur_detail = {}
                for ci in range(data_start_col, len(col_names)):
                    if pd.notna(r.iloc[ci]):
                        k = str(col_names[ci]).strip(); v = str(r.iloc[ci]).strip()
                        cur_detail[k] = cur_detail.get(k, "") + v + "\n"
                continue
        for ci in range(data_start_col, len(col_names)):
            if pd.notna(r.iloc[ci]):
                k = str(col_names[ci]).strip(); v = str(r.iloc[ci]).strip()
                cur_detail[k] = cur_detail.get(k, "") + v + "\n"
    if cur_seq is not None and cur_item:
        result[cur_seq + seq_offset] = {"seq": cur_seq + seq_offset, "item": cur_item, "detail": dict(cur_detail)}
    for v in result.values():
        for dk in list(v["detail"].keys()):
            v["detail"][dk] = v["detail"][dk].strip()
    return result


def parse_detail_v2(xl, sheet_name, seq_offset=0, col_map=None):
    """
    Parse a detail sheet where columns are already separated.
    col_map: optional dict mapping JSON key → Excel column name
    """
    if sheet_name not in xl.sheet_names: return {}
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    hi = find_header_row(df, ["No.", "项目"])
    df.columns = df.iloc[hi].tolist()
    df = df.iloc[hi+1:].reset_index(drop=True)
    col_names = list(df.columns)

    # Find No. and 项目 column indices
    seq_c = None; item_c = None
    for i, c in enumerate(col_names):
        s = str(c).strip()
        if "No" in s or "序号" in s: seq_c = i
        if s == "项目" or s == "测试项目": item_c = i
    if seq_c is None: seq_c = 0
    if item_c is None: item_c = 1

    result = {}
    for _, r in df.iterrows():
        first = r.iloc[seq_c]
        if pd.notna(first):
            try: seq = int(float(first))
            except: continue
            item = str(r.iloc[item_c]).strip() if pd.notna(r.iloc[item_c]) else ""
            detail = {}
            for i, c in enumerate(col_names):
                if i == seq_c or i == item_c: continue
                if pd.notna(r.iloc[i]):
                    k = str(c).strip()
                    v = str(r.iloc[i]).strip()
                    if v: detail[k] = v
            if detail:
                result[seq + seq_offset] = {"seq": seq + seq_offset, "item": item, "detail": detail}
    return result


def parse_longrun_v2(xl, sheet_name, seq_offset=0):
    """Parse 长期运行 (seq in col 1, category in col 0)"""
    if sheet_name not in xl.sheet_names: return {}
    df = pd.read_excel(xl, sheet_name=sheet_name, header=0)
    result = {}
    for _, r in df.iterrows():
        seq = r.iloc[1]
        if pd.notna(seq):
            try: seq_num = int(float(seq))
            except: continue
            item = str(r.iloc[2]).strip() if pd.notna(r.iloc[2]) else ""
            detail = {}
            cols = list(df.columns)
            for ci in range(3, len(r)):
                if ci < len(cols) and pd.notna(r.iloc[ci]):
                    k = str(cols[ci]).strip(); v = str(r.iloc[ci]).strip()
                    detail[k] = v
            if item:
                result[seq_num + seq_offset] = {"seq": seq_num + seq_offset, "item": item, "detail": detail}
    return result


def parse_electrical_v2(xl, sheet_name, seq_offset=0):
    """Parse 电控测试项目"""
    if sheet_name not in xl.sheet_names: return {}
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    hi = find_header_row(df, ["试验项目"])
    df.columns = df.iloc[hi].tolist()
    df = df.iloc[hi+1:].reset_index(drop=True)
    col_names = list(df.columns)

    result = {}
    cur_seq = None; cur_item = None; cur_detail = {}
    for _, r in df.iterrows():
        seq = None
        for c in col_names:
            v = r[c]
            if pd.notna(v):
                try: seq = int(float(v)); break
                except: pass
        if seq is not None:
            item_name = ""
            for c in col_names:
                v = r[c]
                if isinstance(v, str) and len(v) > 2 and not any(str(v).strip().startswith(p) for p in
                       ["测试标准", "试验要求", "判定要求", "验证机型", "电源：", "测试步骤", "截图", "注意事项"]):
                    item_name = str(v).strip(); break
            if cur_seq is not None and cur_item:
                result[cur_seq + seq_offset] = {"seq": cur_seq + seq_offset, "item": cur_item, "detail": dict(cur_detail)}
            cur_seq = seq; cur_item = item_name; cur_detail = {}
            for ci, c in enumerate(col_names):
                if pd.notna(r[c]):
                    k = str(c).strip(); v = str(r[c]).strip()
                    cur_detail[k] = cur_detail.get(k, "") + v + "\n"
        else:
            for ci, c in enumerate(col_names):
                if pd.notna(r[c]):
                    k = str(c).strip(); v = str(r[c]).strip()
                    cur_detail[k] = cur_detail.get(k, "") + v + "\n"
    if cur_seq is not None and cur_item:
        result[cur_seq + seq_offset] = {"seq": cur_seq + seq_offset, "item": cur_item, "detail": dict(cur_detail)}
    for v in result.values():
        for dk in list(v["detail"].keys()):
            v["detail"][dk] = v["detail"][dk].strip()
    return result


def parse_wifi_v2(xl, sheet_name, seq_offset=0):
    """Parse Wifi connectivity test"""
    if sheet_name not in xl.sheet_names: return {}
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    hi = None
    for i, row in df.iterrows():
        if any(isinstance(c, str) and "Test Item" in c for c in row):
            hi = i; break
    if hi is None: return {}
    raw_cols = list(df.iloc[hi])
    new_cols = []
    for i, c in enumerate(raw_cols):
        s = str(c).strip() if pd.notna(c) else ""
        if not s or s.startswith("Unnamed"):
            mapping = {1: "项目", 2: "类别", 3: "测试计划", 4: "测试方法及标准", 5: "负责人"}
            s = mapping.get(i, f"field_{i}")
        new_cols.append(s)
    df.columns = new_cols
    df = df.iloc[hi+1:].reset_index(drop=True)
    col_names = list(df.columns)

    from collections import OrderedDict
    result = {}
    cur_seq = 89 + seq_offset - seq_offset  # use the sheet's own numbering but offset
    # Actually use seq from col 0 if it exists
    seq_c = 0; item_c = None
    for i, c in enumerate(col_names):
        if "项目" in c or "Test Item" in c: item_c = i; break
    if item_c is None: item_c = 1

    for _, r in df.iterrows():
        first = r.iloc[0]
        if pd.notna(first):
            try: seq = int(float(first))
            except: seq = cur_seq
            cur_seq = seq
        else:
            seq = cur_seq
        item = str(r.iloc[item_c]).strip() if pd.notna(r.iloc[item_c]) else ""
        detail = {}
        for ci, c in enumerate(col_names):
            if pd.notna(r.iloc[ci]):
                v = str(r.iloc[ci]).strip()
                if v: detail[c] = v
        if detail:
            result[seq + seq_offset] = {"seq": seq + seq_offset, "item": item or detail.get(col_names[1] if len(col_names)>1 else "", ""), "detail": detail}
    return result


def parse_pump(xl, sheet_name, seq_offset=0):
    """Parse AD-水泵可靠性测试"""
    if sheet_name not in xl.sheet_names: return {}
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    hi = find_header_row(df, ["序号", "测试项目"])
    df.columns = df.iloc[hi].tolist()
    df = df.iloc[hi+1:].reset_index(drop=True)
    col_names = list(df.columns)
    result = {}
    cur_seq = None; cur_item = None; cur_detail = {}
    for _, r in df.iterrows():
        first = r.iloc[0]
        if pd.notna(first):
            try: ns = int(float(first))
            except: ns = None
            if ns is not None and ns != cur_seq:
                if cur_seq is not None and cur_item:
                    result[cur_seq + seq_offset] = {"seq": cur_seq + seq_offset, "item": cur_item, "detail": dict(cur_detail)}
                cur_seq = ns; cur_item = str(r.iloc[1]).strip() if pd.notna(r.iloc[1]) else ""
                cur_detail = {}
                for ci in range(2, len(col_names)):
                    if pd.notna(r.iloc[ci]):
                        k = str(col_names[ci]).strip(); v = str(r.iloc[ci]).strip()
                        cur_detail[k] = cur_detail.get(k, "") + v + "\n"
                continue
        for ci in range(2, len(col_names)):
            if pd.notna(r.iloc[ci]):
                k = str(col_names[ci]).strip(); v = str(r.iloc[ci]).strip()
                cur_detail[k] = cur_detail.get(k, "") + v + "\n"
    if cur_seq is not None and cur_item:
        result[cur_seq + seq_offset] = {"seq": cur_seq + seq_offset, "item": cur_item, "detail": dict(cur_detail)}
    for v in result.values():
        for dk in list(v["detail"].keys()):
            v["detail"][dk] = v["detail"][dk].strip()
    return result


def parse_ptc(xl):
    """Parse PTC 电加热测试 - special format without standard header"""
    sheet_name = "PTC 电加热测试"
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    SUB = ["工况：", "布点：", "电源：", "装机要求：", "开机设置：", "试验过程：", "检查要求：", "截图/照片输出：", "注意事项："]
    result = {}
    cur_item = None; parts = []; item_count = 0

    def flush():
        nonlocal cur_item, parts, item_count
        if cur_item:
            item_count += 1
            result[item_count] = {"seq": item_count, "item": cur_item, "detail": {"全部内容": "\n".join(parts).strip()}}
            parts = []

    for _, r in df.iterrows():
        col1 = str(r.iloc[1]).strip() if len(r) > 1 and pd.notna(r.iloc[1]) else ""
        is_new = len(col1) > 8 and not col1.startswith("Unnamed") and ("测试" in col1 or "试验" in col1)
        if is_new:
            flush()
            cur_item = col1
            for c in r:
                if pd.notna(c):
                    t = str(c).strip()
                    if t and t != cur_item and t != "nan":
                        parts.append(t)
        elif cur_item:
            for c in r:
                if pd.notna(c):
                    t = str(c).strip()
                    if t and t != "nan":
                        parts.append(t)
    flush()
    for k, v in result.items():
        text = v["detail"].get("全部内容", "")
        parsed = {}
        label = None; content = []
        for line in text.replace("\\n", "\n").split("\n"):
            ls = line.strip()
            matched = None
            for lb in SUB:
                if ls.startswith(lb): matched = lb; break
            if matched:
                if label and content: parsed[label] = "\n".join(content).strip()
                label = matched; content = [ls[len(matched):]] if ls[len(matched):] else []
            elif label: content.append(ls)
        if label and content: parsed[label] = "\n".join(content).strip()
        v["detail"] = parsed if parsed else {"全部内容": text}
    return result


# ══════════════════════════════════════════════
# Main build
# ══════════════════════════════════════════════

all_cat_items = {}
all_details = {}
all_sheet_map = {}
product_list = []

for fname, product, offset in PRODUCTS:
    xl = pd.ExcelFile(fname)
    print(f"\n=== {product} ({fname}) ===")

    # Master
    cats, cat_items, _ = parse_master(xl, product, offset)

    # Detail sheets
    details = {}

    if product == "移动空调":
        # AC-specific detail parsers
        details["testMethod"] = parse_detail_sheet(xl, "测试方法", offset)
        details["safety"] = parse_detail_sheet(xl, "UL60335安规", offset)
        details["electrical"] = parse_electrical_v2(xl, "电控测试项目", offset)
        details["wifi"] = parse_wifi_v2(xl, "Wifi connectivity test", offset)
        details["longrun"] = parse_longrun_v2(xl, "长期运行", offset)
        # PTC
        ptc_raw = parse_ptc(xl)
        if ptc_raw:
            ptc_offset = 200
            ptc_items = sorted(ptc_raw.keys())
            ptc_d = {}
            for i, ok in enumerate(ptc_items):
                nk = ptc_offset + 1 + i
                v = ptc_raw[ok]; v["seq"] = nk; v["item"] = v.get("item", "")
                ptc_d[str(nk)] = v
                cat_items.setdefault("PTC 电加热测试", []).append(
                    {"cat": "PTC 电加热测试", "seq": nk, "item": v["item"], "std": "", "product": product})
            if "PTC 电加热测试" not in cats: cats.append("PTC 电加热测试")
            details["ptc"] = ptc_d
            print(f"  ptc: {len(ptc_d)} items")

        sheet_map = {
            "包装测试": ["testMethod"], "性能测试": ["testMethod"],
            "噪音振动类": ["testMethod"], "性能可靠性": ["testMethod"],
            "UL60335安规": ["safety"],
            "电控类(整机)": ["electrical"], "电控类(PCBA)": ["electrical"],
            "Wifi connectivity test": ["wifi"],
            "长期运行": ["longrun"], "EMC": [],
            "PTC 电加热测试": ["ptc"],
        }

    else:  # 除湿机
        details["method_v2"] = parse_detail_v2(xl, "测试方法汇总 (2)", offset)
        details["safety"] = parse_detail_sheet(xl, "安规测试方法", offset, seq_col_idx=0, item_col_idx=1, data_start_col=2)
        details["electrical"] = parse_electrical_v2(xl, "电控测试项目", offset)
        details["wifi"] = parse_wifi_v2(xl, "Wifi connectivity test", offset)
        details["longrun"] = parse_longrun_v2(xl, "长期运行测试方法", offset)
        details["pump"] = parse_pump(xl, "AD-水泵可靠性测试", offset)

        # Add categories that exist in master
        sheet_map = {}
        method_v2_cats = ["能力", "净化", "噪音", "能效", "包装", "结构", "功能", "可靠性"]
        for c in cats:
            if any(m in c for m in method_v2_cats):
                sheet_map[c] = ["method_v2"]
            elif "安规" in c or c == "安全":
                sheet_map[c] = ["safety"]
            elif "电控" in c:
                sheet_map[c] = ["electrical"]
            elif "长期" in c:
                sheet_map[c] = ["longrun"]
            elif "Wifi" in c:
                sheet_map[c] = ["wifi"]
            elif "水泵" in c:
                sheet_map[c] = ["pump"]
            elif "EMC" in c.replace("（", "("):
                sheet_map[c] = []
            else:
                sheet_map[c] = []

        # Add pump category if not in master
        pump_exists = any("水泵" in c for c in cats)
        if not pump_exists:
            pump_data = details.get("pump", {})
            if pump_data:
                pump_cat = "AD-水泵可靠性测试"
                cats.append(pump_cat)
                pump_master = []
                for k, v in sorted(pump_data.items(), key=lambda x: int(x[0])):
                    pump_master.append({"cat": pump_cat, "seq": v["seq"], "item": v["item"], "std": "", "product": product})
                cat_items[pump_cat] = pump_master
                sheet_map[pump_cat] = ["pump"]

        # Add refrigerant leakage category
        leak_exists = any("制冷剂" in c for c in cats)
        if "制冷剂缺少测试方法" in xl.sheet_names:
            if not leak_exists:
                leak_cat = "制冷剂缺少测试"
                cats.append(leak_cat)
                df = pd.read_excel(xl, sheet_name="制冷剂缺少测试方法", header=None)
                content = "\n".join(str(c) for _, r in df.iterrows() for c in r if pd.notna(c))
                leak_item = {"cat": leak_cat, "seq": offset + 90, "item": "制冷剂缺少测试", "std": "", "product": product}
                cat_items[leak_cat] = [leak_item]
                details["refrigerant"] = {str(offset + 90): {"seq": offset + 90, "item": "制冷剂缺少测试", "detail": {"全部内容": content}}}
                sheet_map[leak_cat] = ["refrigerant"]

        print(f"  method_v2: {len(details['method_v2'])} items")
        if details.get("safety"): print(f"  safety: {len(details['safety'])} items")
        if details.get("electrical"): print(f"  electrical: {len(details['electrical'])} items")
        if details.get("wifi"): print(f"  wifi: {len(details['wifi'])} items")
        if details.get("longrun"): print(f"  longrun: {len(details['longrun'])} items")
        if details.get("pump"): print(f"  pump: {len(details['pump'])} items")
        if details.get("refrigerant"): print(f"  refrigerant: 1 item")
        cats.sort()

    # Post-process all detail records
    for name in list(details.keys()):
        for k, v in details[name].items():
            if "detail" in v:
                v["detail"] = clean_detail(v["detail"])
                v["detail"] = split_combined(v["detail"])

    # Merge into global
    for c in cats:
        for it in cat_items.get(c, []):
            all_cat_items.setdefault(c, []).append(it)
        if c not in all_sheet_map:
            all_sheet_map[c] = sheet_map.get(c, [])

    for name, data in details.items():
        all_details.setdefault(name, {}).update(data)

    product_list.append(product)

# Build final categories with product prefix
final_cats = []
final_cat_items = {}
final_sheet_map = {}
seen = set()

for product in product_list:
    for c in sorted(all_cat_items.keys()):
        items = all_cat_items[c]
        product_items = [it for it in items if it.get("product") == product]
        if not product_items:
            continue
        pcat = f"{product} - {c}"
        if pcat in seen:
            continue
        seen.add(pcat)
        final_cat_items[pcat] = product_items
        final_sheet_map[pcat] = all_sheet_map.get(c, [])
        final_cats.append(pcat)

output = {
    "products": product_list,
    "categories": final_cats,
    "categoryItems": final_cat_items,
    "details": all_details,
    "catSheetMap": final_sheet_map,
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=1)
print(f"\nSaved {OUTPUT} ({len(json.dumps(output, ensure_ascii=False))} bytes)")
print(f"Categories: {final_cats}")
for c in final_cats:
    print(f"  {c}: {len(final_cat_items[c])} items")
