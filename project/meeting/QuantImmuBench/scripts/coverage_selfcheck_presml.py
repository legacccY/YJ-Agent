"""slice_presml 覆盖自检：逐工具核 official 覆盖，缺格子逐条归因(正常过滤 vs 真漏)。
铁律=不能漏；缺必显式记原因。"""
import csv, pathlib
BASE = pathlib.Path(r"D:\YJ-Agent\project\meeting\QuantImmuBench")
BB = BASE / "scripts/out_rerun/master_backbone_official.csv"
OFF = BASE / "scripts/out_rerun_official"

# 读 backbone
bb = list(csv.DictReader(open(BB, encoding="utf-8")))
N = len(bb)
print(f"backbone: {N} bb_idx 行, {len(set(r['HLA_Allele'] for r in bb))} HLA\n")

# HLAthena ecdf 覆盖等位(来自跑时 log)
ECDF = set("A0101 A0201 A0203 A0205 A0206 A0207 A0301 A2402 A2501 A3001 A3101 A3201 A6601 "
           "B0702 B0801 B1302 B1501 B1801 B2705 B3503 B3507 B3801 B4001 B4006 B4402 B5501 B5701 "
           "C0202 C0303 C0304 C0401 C0501 C0602 C0701 C0702 C0801 C1203".split())
def prime(h): return h.replace("HLA-","").replace("*","").replace(":","")

TOOLS = {
    "MHCflurry":  ("MHCflurry_official.csv",  ["MT_MHCflurry_presentation","WT_MHCflurry_presentation",
                                               "MT_MHCflurry_affinity_neg","WT_MHCflurry_affinity_neg"]),
    "TransHLA":   ("TransHLA_official.csv",   ["MT_TransHLA","WT_TransHLA"]),
    "MHCSeqNet":  ("MHCSeqNet_official.csv",  ["MT_MHCSeqNet","WT_MHCSeqNet"]),
    "MHCnuggets": ("MHCnuggets_official.csv", ["MT_MHCnuggets","WT_MHCnuggets"]),
    "HLAthena":   ("HLAthena_official.csv",   ["MT_HLAthena","WT_HLAthena"]),
}

all_ok = True
for tool,(fn,cols) in TOOLS.items():
    p = OFF/fn
    if not p.exists():
        print(f"❌ {tool}: official 不存在"); all_ok=False; continue
    rows = list(csv.DictReader(open(p,encoding="utf-8")))
    print(f"===== {tool} ({len(rows)} 行) =====")
    if len(rows)!=N:
        print(f"  ❌ 行数 {len(rows)} ≠ backbone {N}!"); all_ok=False
    for col in cols:
        filled = sum(1 for r in rows if r.get(col,"").strip() not in ("","nan","NaN"))
        pct = 100*filled/len(rows)
        # 归因 NaN
        nan_idx = [i for i,r in enumerate(rows) if r.get(col,"").strip() in ("","nan","NaN")]
        if tool=="HLAthena":
            side = "MT_Subpeptide" if col.startswith("MT") else "WT_Subpeptide"
            b2706 = sum(1 for i in nan_idx if bb[i]["HLA_Allele"]=="HLA-B*27:06")
            noecdf = sum(1 for i in nan_idx if prime(bb[i]["HLA_Allele"]) not in ECDF)
            other = len(nan_idx) - noecdf
            tag = f"NaN={len(nan_idx)} [无ecdf等位(正常)={noecdf}(含B2706), 其余={other}(肽级未打分/端部)]"
            print(f"  {col:32s} {filled}/{len(rows)} ({pct:.1f}%)  {tag}")
        else:
            status = "✅100%" if pct>99.9 else f"⚠️{pct:.1f}% NaN={len(nan_idx)}"
            print(f"  {col:32s} {filled}/{len(rows)} ({pct:.1f}%)  {status}")
            if pct<99.9: all_ok=False
    print()

# HLAthena 专项：确认非 ecdf-缺 之外无真漏
print("===== HLAthena 缺格归因(命门) =====")
ha = list(csv.DictReader(open(OFF/"HLAthena_official.csv",encoding="utf-8")))
by_hla_total, by_hla_nan = {}, {}
for i,r in enumerate(ha):
    h = bb[i]["HLA_Allele"]
    by_hla_total[h] = by_hla_total.get(h,0)+1
    if r.get("MT_HLAthena","").strip() in ("","nan","NaN"):
        by_hla_nan[h] = by_hla_nan.get(h,0)+1
print(f"{'HLA':16s} {'总':>5s} {'MT_NaN':>7s}  归因")
real_miss = 0
for h in sorted(by_hla_total):
    tot=by_hla_total[h]; nan=by_hla_nan.get(h,0)
    has_ecdf = prime(h) in ECDF
    if not has_ecdf:
        reason = "无ecdf模型(正常,文档记录)"
    elif nan==0:
        reason = "全覆盖"
    else:
        reason = f"⚠️有ecdf却{nan}缺→查(肽级/端部?)"; real_miss += nan
    print(f"{h:16s} {tot:5d} {nan:7d}  {reason}")
print(f"\n有 ecdf 但仍缺(潜在真漏,需查): {real_miss}")
print(f"\n{'✅ 自检通过：非HLAthena工具全100%,HLAthena缺格全归因' if all_ok and real_miss==0 else '⚠️ 有需复查项(见上)'}")
