# -*- coding: utf-8 -*-
"""
prep_hlathena_ctx_FULL130.py — QuantImmuBench 覆盖修复战役 / HLAthena MSiCE 正式输入builder
服务: quantimmu-bench §工具部署  lever=HLAthena presentation proxy 覆盖补满 (DS2 101->130)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️⚠️ HLAthena 预测 MHC-I **提呈(presentation) 不是免疫原性**(Sarkizova 2020 Nat
   Biotech)。进 benchmark 只作 presentation baseline proxy，单列呈现，绝不与免疫
   原性工具 apples-to-apples 并列。方向照原: MSi/MSiCE 越高越提呈，无翻转。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【为什么要这个脚本 / 与旧 prep 的区别】
  旧 prep_hlathena_hpc.py 只写**纯肽列表**(无表头, 一列肽) -> 只能跑最简 MSi 模型。
  本脚本产 HLAthena 官方 **MSiCE 输入**(cleavage-context + expression), 让 sif 内置
  predict 用上下文+表达量特征, 且格式对得上容器示例 /pred/test/peps.txt, 才不会静默失败。
  同时把 DS2 覆盖从 merged 里的 101 肽 (仅 SNV, MT!=WT 9mer) 补到官方 130 肽全量
  (含 29 个 indel/frameshift, 它们无 WT 故被旧 m9 过滤器漏掉)。

【HLAthena predict 输入格式 —— 来源与口径 (researcher 联网核实, 官方 hlathena.tools 明文)】
  tab 分隔 + 表头, 列 = pep  len  ctex_up  ctex_dn  TPM  log2TPM
  容器示例 /pred/test/peps.txt (主线从 sif 内核实):
    pep       len  ctex_up(30aa)                    ctex_dn(30aa)                    TPM   log2TPM
    IDLLKEIY  8    AAAAAALVSDSFSCGGSPGSSAFSLTSSSA   ASSSPFANDYSVFQAPGVSGGSGGGGGGGG   30.2  4.963474124
  口径 (官方 http://hlathena.tools/ 文档 + Bash 自核, 见下逐条):
   · ctex_up / ctex_dn = 各 **30 个氨基酸** (官方明文 "30 upstream and 30 downstream")。 [核实]
   · 不足 30 (肽靠近序列边界) -> **补 dash '-'** (官方明文 "padded with dashes '-'")。 [核实]
       示例里 "AAAAAA"/"GGGGGGGG" 是源蛋白真实低复杂度序列, 不是 padding (padding 只用 '-')。
   · log2TPM = **log2(TPM + 1)**。 [Bash 自核: log2(30.2+1)=4.963474124 命中示例; log2(30.2)=4.9165 不匹配]
   · 方向 (ctex_up/dn 的 N->C 写向): **推断** ctex_up 按 N->C 正向 (紧邻肽 N 端的残基在
       ctex_up 最右; padding 补在最左/远端), ctex_dn 同 (紧邻肽 C 端残基在最左; padding 补右)。
       ⚠️ TODO(方向): 官方 doc/正文未明示 N->C vs 反向, 上为惯例推断。若 sif 跑出的 MSiC 分
       与官方 peps.txt 回归测试对不上, 优先怀疑方向翻转, 主线可 exec 进容器读 /encoding 源码坐实。
       [来源: http://hlathena.tools/ ; Sarkizova 2020 PMC7008090 ; docker ssarkizova/hlathena-external]

【本项目侧翼上下文口径 (与原 HLAthena "取源蛋白 30aa" 的偏离说明 —— 诚实标注)】
  ⚠️ 原 HLAthena 的 ctex 取自**完整源蛋白**上下游 30aa。本 benchmark 的肽来自**合成长疫苗肽**
  (synthetic long peptide, 15-33 aa), 冻结数据里**没有完整源蛋白序列**, 只有疫苗肽本身。
  故本脚本 ctex 只能从**完整疫苗肽内部**截 (子肽两侧疫苗肽内可得的全部 aa), 不足 30 补 '-'。
  这是给定冻结数据下**最合理且唯一可得**的默认 (任务显式许可: "查不到确切口径用最合理默认——
  前后各截完整疫苗肽里子肽两侧全部可得 aa")。后果: 因疫苗肽短, ctex 绝大多数是 dash-heavy
  (真实上下文只有几个 aa)。这对 MSiC/MSiCE 的 cleavage 特征是弱化但无泄漏, 且**全 130 肽同口径**,
  组内可比。⚠️ 与"取真源蛋白 30aa"的原口径不同 —— 结果表须标 "context = vaccine-peptide-internal"。

【子肽口径 (复现原 benchmark m9 + 补 indel)】
  · in-benchmark 肽 (merged m9 里的 101 个, 全 SNV): **原样复用** merged 的 9mer 含突变子肽
    (MT_Subpeptide != WT_Subpeptide, 即含突变残基的 9mer 窗口) + 其 bb_idx/Position/HLA。
    每个子肽产 MT 行 + WT 行 (WT 侧翼取自 WT_FullPeptide)。=> 复现零偏离, 过重叠审计。
  · extra 肽 (官方 130 里 merged 缺的 29 个: 23 DEL + 5 INS + 1 SNV): merged 无它们的行,
    从 GT Vaccine_Peptide **滑窗生成全部 9mer 窗口** (MT only, 无 WT)。理由: indel/frameshift
    的整条疫苗肽都是 neoORF 新序列, 所有 9mer 皆"突变来源"; 无 WT 对应物。这 29 个不在原
    benchmark 表里 (无 bb_idx), 故给合成 id "CTXNEW-<pid>-<pos>", bb_map 标 in_benchmark=0,
    供主线决定是否为它们在 benchmark 表新增行。

【等位 (allele) 覆盖】
  · in-benchmark 肽: 用 merged 每行自带的 HLA_Allele (= 该患者 HLA 分型, 与原 benchmark 一致)。
  · extra 肽: 用**同患者**在既有 hlathena_input_FULL130.csv (DS2) 里的等位集合 (= benchmark
    实际给该患者用的分型), 保证等位 tag 与既有 HLAthena 列一致。
  · tag = HLA-A*66:01 -> A6601 (去 HLA- 去 * 去 :)。
  · ⚠️ 哪些 tag 有 specific 模型 (真覆盖) 由 HPC 上 $ROOT/hla_arr/models 运行时判定 (旧 prep 同逻辑);
    本脚本本地不判, 为**所有** tag 都写 .pep 文件, 主线 run 时只跑有模型的 (无模型 -> 整组 NaN)。

【TPM 缺失】
  ⚠️ GT 里 13 个肽无 RNA TPM (患者 107 全部 10 肽 + 104-24 + ...): 这些行 TPM/log2TPM 留空。
  含义: 它们只能跑 MSiC (context, 无 expression) 不能跑 MSiCE。bb_map 有 has_tpm 标, manifest
  有 n_notpm 计数。主线决定: 对无 TPM 行改跑 MSiC (丢 TPM 两列) 或让 predict 按空 TPM 处理。
  TODO(主线): 用 sif `predict --help` 核实空 TPM 时 predict 的模型选择行为 (是否自动降 MSiC)。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【产出 (默认写到本脚本同目录 HPC/deploy/hlathena/)】
  hlathena_ctx_inputs/<tag>.pep   —— 每个 covered-候选 allele 的 MSiCE 输入 TSV
                                     (tab + 表头 pep/len/ctex_up/ctex_dn/TPM/log2TPM,
                                      按 (pep,ctex_up,ctex_dn,TPM) 去重)
  bb_map.csv                       —— 每 (子肽实例 x allele x MT/WT) 一行, 回贴映射:
                                     bb_idx,in_benchmark,tag,HLA_Allele,Patient_ID,Peptide_ID,
                                     mut_key,source,is_indel,position,pep,len,ctex_up,ctex_dn,
                                     TPM,log2TPM,has_tpm
                                     (parse 用 (tag,pep,ctex_up,ctex_dn) 精确 join 分数回贴)
  alleles_manifest.csv             —— tag,original_hla,n_pep,n_notpm,pep_file

【主线在 HPC 上怎么用 sif 跑 (本窗只 build, 不连 HPC 不跑工具)】
  逐 allele (manifest 里每个 tag) 调 sif 内置 predict:
    singularity exec \
        -B $ROOT/hla_arr/models:/models:ro \
        -B $ROOT/hla_arr/models_panpan:/models_panpan:ro \
        -B <work>:/work \
        $ROOT/sif/hlathena.sif \
        predict --runID <tag> --rundir /work \
                --peptides /work/hlathena_ctx_inputs/<tag>.pep \
                --alleles <tag>
    -> 产 /work/<tag>-predictions.txt (17 列含 MSi_<tag>/MSiC/MSiCE 提呈分)。
  ⚠️ predict 具体如何吃 ctex/TPM 列、如何在 MSi/MSiC/MSiCE 间选模型 (是否需 --model 或
     exists_ctex/exists_expr flag): 主线先 `singularity exec $SIF predict --help` 核实,
     必要时改 --peptides 列组合 (MSiC=丢 TPM/log2TPM 两列; MSiCE=全 6 列)。
  回贴: ctex-aware parse 按 (tag,pep,ctex_up,ctex_dn) 匹配 bb_map -> 填 MT_HLAthena/WT_HLAthena。
     (旧 parse_hlathena_hpc.py 只按 pep 匹配, MSiCE 下同一 pep 不同 ctex 会歧义 -> 需升级为
      ctex-aware, 见 bb_map 已带 ctex_up/ctex_dn 两列供精确 join。)

⚠️ 本脚本纯本地 pandas: 只建输入文件, 绝不连 HPC / 不跑工具 / 不 pip。Windows/pathlib/UTF-8。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")
CTX_LEN = 30                       # HLAthena ctex_up/ctex_dn 官方长度 (核实)
PAD = "-"                          # 官方 padding 字符 (核实)
DS2_PATIENTS = [101, 102, 104, 105, 106, 107, 108, 109, 110]  # 硬约束: 只 DS2 130 肽

# 项目根 = 本脚本 parents[3] (HPC/deploy/hlathena/ -> QuantImmuBench/)
ROOT = Path(__file__).resolve().parents[3]


def hla_to_tag(h: str) -> str:
    """HLA-A*66:01 -> A6601 (去 HLA- 去 * 去 :)。"""
    return str(h).replace("HLA-", "").replace("*", "").replace(":", "").strip()


def norm_pid(pid: str) -> str:
    """归一 Peptide_ID: 末段去前导零, 消 GT/merged 的 02 vs 2 padding 不一致。"""
    p = str(pid).split("-")
    return f"{p[0]}-{p[1]}-{int(p[2])}" if len(p) == 3 and p[2].isdigit() else str(pid)


def is_clean(pep: str) -> bool:
    return bool(pep) and all(c in STD_AA for c in pep)


def make_ctex(full: str, start0: int, plen: int):
    """从完整肽 full 里, 子肽 [start0, start0+plen) 两侧截 30aa 上下文, 不足补 '-'.
    方向 = N->C 正向 (ctex_up 最右紧邻肽 N 端; ctex_dn 最左紧邻肽 C 端; padding 补远端)。
    返回 (ctex_up, ctex_dn), 各 len==CTX_LEN。"""
    before = full[:start0]                    # 肽 N 端上游 (N->C 顺序, 右端紧邻肽)
    after = full[start0 + plen:]              # 肽 C 端下游 (N->C 顺序, 左端紧邻肽)
    ctex_up = before[-CTX_LEN:].rjust(CTX_LEN, PAD)   # 取最近 30, 左端补 '-'
    ctex_dn = after[:CTX_LEN].ljust(CTX_LEN, PAD)     # 取最近 30, 右端补 '-'
    return ctex_up, ctex_dn


def log2tpm(tpm):
    """log2(TPM+1); TPM 为空/NaN -> None。"""
    if tpm is None:
        return None
    try:
        t = float(tpm)
    except (TypeError, ValueError):
        return None
    if math.isnan(t):
        return None
    return math.log2(t + 1.0)


def main():
    ap = argparse.ArgumentParser(description="HLAthena MSiCE ctex 输入 builder (DS2 全 130 肽)")
    ap.add_argument("--gt", default=str(ROOT / "data" / "frozen" / "ds2_official_groundtruth.csv"),
                    help="DS2 官方 ground truth (Vaccine_Peptide/TPM/mut_key)")
    ap.add_argument("--merged", default=str(ROOT / "scripts" / "out" / "merged_all_tools_29tools.xlsx"),
                    help="merged 全工具表 (SNV 子肽 + Position + WT_FullPeptide + bb_idx + HLA)")
    ap.add_argument("--existing-input",
                    default=str(ROOT / "HPC" / "deploy" / "hlathena" / "hlathena_input_FULL130.csv"),
                    help="既有 HLAthena 输入 (取每患者等位集合, 给 extra 肽用)")
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parent),
                    help="输出根目录 (默认本脚本同目录)")
    args = ap.parse_args()

    gt_path = Path(args.gt)
    merged_path = Path(args.merged)
    existing_path = Path(args.existing_input)
    outdir = Path(args.outdir)
    pepdir = outdir / "hlathena_ctx_inputs"
    pepdir.mkdir(parents=True, exist_ok=True)

    for p in (gt_path, merged_path, existing_path):
        if not p.exists():
            raise SystemExit(f"[FAIL] 数据源不存在: {p}")

    # ── 读 GT (DS2 130 肽) ──────────────────────────────────────────────────────────
    gt = pd.read_csv(gt_path)
    gt = gt[gt["Patient_ID"].isin(DS2_PATIENTS)].copy()
    gt["pn"] = gt["Peptide_ID"].map(norm_pid)
    tpm_by_pn = gt.set_index("pn")["TPM_PurifiedTumorRNA"].to_dict()
    mutkey_by_pn = gt.set_index("pn")["mut_key"].to_dict()
    vacc_by_pn = gt.set_index("pn")["Vaccine_Peptide"].to_dict()
    patient_by_pn = gt.set_index("pn")["Patient_ID"].to_dict()
    print(f"[gt]  DS2 ground-truth 肽 = {len(gt)} (patients {sorted(gt['Patient_ID'].unique())})")

    # ── 读既有输入 -> 每患者等位集合 (给 extra 肽) ────────────────────────────────────
    exist = pd.read_csv(existing_path)
    exist = exist[exist["Dataset"] == "DS2"]
    patient_alleles = {int(p): sorted(g["HLA_Allele"].unique())
                       for p, g in exist.groupby("Patient_ID")}

    # ── 读 merged, 取 DS2 m9 (9mer 含突变子肽, MT!=WT) = in-benchmark 的 101 肽 ─────────
    mg = pd.read_excel(merged_path)
    mg = mg[(mg["Dataset"] == "DS2") & mg["Patient_ID"].isin(DS2_PATIENTS)].copy()
    mg["L"] = mg["MT_Subpeptide"].astype(str).str.len()
    m9 = mg[(mg["L"] == 9) &
            (mg["MT_Subpeptide"].astype(str) != mg["WT_Subpeptide"].astype(str))].copy()
    m9 = m9.dropna(subset=["MT_Subpeptide", "HLA_Allele"])
    m9["pn"] = m9["Peptide_ID"].map(norm_pid)
    in_bench_pns = set(m9["pn"].unique())
    print(f"[merged] DS2 m9 行 = {len(m9)} | in-benchmark 肽 = {len(in_bench_pns)} (SNV, MT!=WT 9mer)")

    # extra 肽 = GT 里但 merged m9 缺的 (indel/frameshift + 个别 SNV)
    all_pns = set(gt["pn"].unique())
    extra_pns = sorted(all_pns - in_bench_pns)
    print(f"[extra] merged 缺的 DS2 肽 = {len(extra_pns)} (滑窗全 9mer, MT only, 无 WT)")

    # ── 累积记录: 每 (tag, subpeptide 实例, MT/WT) 一条 ─────────────────────────────────
    records = []   # dict per 行
    n_len_drop = n_aa_drop = 0

    def add_record(tag, hla, pn, source, is_indel, position, full, start0, pep):
        """加一条子肽记录 (含 ctex + TPM)。pep 已确保 9mer 标准 AA。"""
        nonlocal n_aa_drop
        if not is_clean(pep):
            n_aa_drop += 1
            return
        ctex_up, ctex_dn = make_ctex(full, start0, len(pep))
        tpm = tpm_by_pn.get(pn)
        try:
            tpm_v = float(tpm)
            if math.isnan(tpm_v):
                tpm_v = None
        except (TypeError, ValueError):
            tpm_v = None
        l2 = log2tpm(tpm_v)
        records.append({
            "tag": tag,
            "HLA_Allele": hla,
            "Patient_ID": patient_by_pn.get(pn),
            "Peptide_ID": pn,
            "mut_key": mutkey_by_pn.get(pn, ""),
            "source": source,           # MT / WT
            "is_indel": int(is_indel),
            "position": position,        # 1-based start in full peptide
            "pep": pep,
            "len": len(pep),
            "ctex_up": ctex_up,
            "ctex_dn": ctex_dn,
            "TPM": ("" if tpm_v is None else f"{tpm_v:.10g}"),
            "log2TPM": ("" if l2 is None else f"{l2:.10g}"),
            "has_tpm": int(tpm_v is not None),
        })

    # ── (A) in-benchmark 101 肽: 复用 merged m9 子肽 + bb_idx + Position (MT + WT) ───────
    for r in m9.itertuples(index=False):
        d = r._asdict()
        pn = d["pn"]
        tag = hla_to_tag(d["HLA_Allele"])
        pos = int(d["Position"])                     # 1-based
        start0 = pos - 1
        mt_full = str(d["MT_FullPeptide"])
        mt_sub = str(d["MT_Subpeptide"]).strip().upper()
        wt_full = str(d["WT_FullPeptide"])
        wt_sub = str(d["WT_Subpeptide"]).strip().upper()
        bb = str(d["bb_idx"]).strip()

        # MT 行 (侧翼取自 MT_FullPeptide = Vaccine_Peptide)
        if len(mt_sub) == 9:
            rec_i = len(records)
            add_record(tag, d["HLA_Allele"], pn, "MT", False, pos, mt_full, start0, mt_sub)
            if rec_i < len(records):
                records[-1]["bb_idx"] = bb
                records[-1]["in_benchmark"] = 1
        else:
            n_len_drop += 1

        # WT 行 (侧翼取自 WT_FullPeptide; WT 子肽在 WT 全肽里同 Position 对齐)
        if wt_sub and wt_sub != "NAN" and len(wt_sub) == 9 and len(wt_full) >= start0 + 9:
            # 确认 WT 子肽在 WT 全肽同位 (SNV 同长, Position 对齐)
            wt_at = wt_full[start0:start0 + 9]
            wstart0 = start0 if wt_at == wt_sub else wt_full.find(wt_sub)
            if wstart0 >= 0:
                rec_i = len(records)
                add_record(tag, d["HLA_Allele"], pn, "WT", False, wstart0 + 1, wt_full, wstart0, wt_sub)
                if rec_i < len(records):
                    records[-1]["bb_idx"] = bb
                    records[-1]["in_benchmark"] = 1

    # ── (B) extra 29 肽: GT Vaccine_Peptide 滑窗全 9mer (MT only) ────────────────────────
    for pn in extra_pns:
        vacc = str(vacc_by_pn.get(pn, "")).strip().upper()
        pat = int(patient_by_pn.get(pn))
        is_indel = True   # extra 里绝大多是 indel/frameshift; 1 个 SNV 也走全窗 (无 WT 可 diff)
        alleles = patient_alleles.get(pat, [])
        if not alleles:
            print(f"[extra][WARN] 患者 {pat} 无既有等位集合, 肽 {pn} 跳过")
            continue
        if len(vacc) < 9 or not is_clean(vacc):
            continue
        for start0 in range(0, len(vacc) - 9 + 1):
            pep = vacc[start0:start0 + 9]
            for hla in alleles:
                tag = hla_to_tag(hla)
                rec_i = len(records)
                add_record(tag, hla, pn, "MT", is_indel, start0 + 1, vacc, start0, pep)
                if rec_i < len(records):
                    records[-1]["bb_idx"] = f"CTXNEW-{pn}-{start0 + 1}"
                    records[-1]["in_benchmark"] = 0

    if not records:
        raise SystemExit("[FAIL] 无任何子肽记录, 检查数据源")

    df = pd.DataFrame(records)
    # 缺省列补齐 (add_record 里若 AA 脏未加 bb_idx/in_benchmark)
    for col, dv in (("bb_idx", ""), ("in_benchmark", 0)):
        if col not in df.columns:
            df[col] = dv
    df["bb_idx"] = df["bb_idx"].fillna("")
    df["in_benchmark"] = df["in_benchmark"].fillna(0).astype(int)

    print(f"[build] 子肽记录总行 = {len(df)} "
          f"(MT={ (df['source']=='MT').sum() } / WT={ (df['source']=='WT').sum() })")
    print(f"[build] 覆盖 DS2 肽 = {df['Peptide_ID'].nunique()} / 130 "
          f"(in-benchmark={df[df.in_benchmark==1]['Peptide_ID'].nunique()} "
          f"+ extra={df[df.in_benchmark==0]['Peptide_ID'].nunique()})")
    print(f"[build] 丢弃: len!=9={n_len_drop} | 非标准AA={n_aa_drop}")

    # ── 写 per-allele .pep (tab + 表头, 按 (pep,ctex_up,ctex_dn,TPM) 去重) ───────────────
    tags = sorted(df["tag"].unique())
    orig_by_tag = df.drop_duplicates("tag").set_index("tag")["HLA_Allele"].to_dict()
    manifest_rows = []
    for tag in tags:
        sub = df[df["tag"] == tag]
        uniq = sub.drop_duplicates(["pep", "ctex_up", "ctex_dn", "TPM"])[
            ["pep", "len", "ctex_up", "ctex_dn", "TPM", "log2TPM"]
        ].copy()
        pep_file = pepdir / f"{tag}.pep"
        uniq.to_csv(pep_file, sep="\t", index=False, encoding="utf-8", lineterminator="\n")
        n_notpm = int((uniq["TPM"].astype(str).str.strip() == "").sum())
        manifest_rows.append({
            "tag": tag,
            "original_hla": orig_by_tag.get(tag, ""),
            "n_pep": len(uniq),
            "n_notpm": n_notpm,
            "pep_file": str(pep_file.relative_to(outdir)),
        })

    # ── 写 bb_map.csv (全列, 供 ctex-aware parse 回贴) ─────────────────────────────────
    bb_cols = ["bb_idx", "in_benchmark", "tag", "HLA_Allele", "Patient_ID", "Peptide_ID",
               "mut_key", "source", "is_indel", "position", "pep", "len",
               "ctex_up", "ctex_dn", "TPM", "log2TPM", "has_tpm"]
    df[bb_cols].to_csv(outdir / "bb_map.csv", index=False, encoding="utf-8")

    # ── 写 alleles_manifest.csv ──────────────────────────────────────────────────────
    mf = pd.DataFrame(manifest_rows)
    mf.to_csv(outdir / "alleles_manifest.csv", index=False, encoding="utf-8")

    # ── 汇报 ─────────────────────────────────────────────────────────────────────────
    print("\n==== per-allele 输出 (hlathena_ctx_inputs/<tag>.pep) ====")
    print(mf.to_string(index=False))
    print(f"\n[out] bb_map.csv           -> {outdir / 'bb_map.csv'} ({len(df)} 行)")
    print(f"[out] alleles_manifest.csv -> {outdir / 'alleles_manifest.csv'} ({len(mf)} tag)")
    print(f"[out] per-allele .pep      -> {pepdir}/ ({len(tags)} 文件)")
    n_notpm_pep = df[df.has_tpm == 0]["Peptide_ID"].nunique()
    print(f"\n[QC] 覆盖肽 = {df['Peptide_ID'].nunique()}/130 | "
          f"无 TPM 肽 = {n_notpm_pep} (只能 MSiC) | 有 TPM 肽 = {df[df.has_tpm==1]['Peptide_ID'].nunique()}")
    print("[QC] 样例行 (首个 tag 的 .pep 前 3 行):")
    ex_tag = tags[0]
    with open(pepdir / f"{ex_tag}.pep", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i > 3:
                break
            print("   ", repr(line.rstrip("\n")))
    print(f"\n⚠️ ctex = vaccine-peptide-internal (非源蛋白 30aa, 冻结数据无源蛋白); dash-heavy 属正常。")
    print("⚠️ HLAthena = presentation proxy, 非免疫原性; 下游单列, 无翻转。")


if __name__ == "__main__":
    main()
