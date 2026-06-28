# -*- coding: utf-8 -*-
"""
run_tscape_101102.py — Phase B：用订正 HLA 等位重推理 T-SCAPE（P101/P102）。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（4018 行，已过闸门：
HLA_Allele == 订正真值 P101={A*66:01,B*40:01,B*57:01,C*06:02}/
P102={A*02:01,B*35:03,B*38:01}）。本脚本只从这份派生，绝不读旧 tscape 输入文件。
T-SCAPE 是 MT-only 工具（只需肽+HLA）→ 只取 MT_Subpeptide，只产 MT_TSCAPE 列。

自包含三步（prep+run+parse 一体），与 HPC/deploy/tscape 三件套调用逻辑一致：
  1. prep：从 backbone 取 MT_Subpeptide + HLA_Allele，去重成 unique (peptide, allele) 对，
     写官方 pmhc_im 输入 CSV（列名 `Allele,peptide`——peptide 列名必小写，核
     example/inputs/pmhc_im.csv；HLA 保持 WHO 格式 HLA-A*02:01 无需转换；peptide 值原样大写）。
     ≤20mer，超长跳过置 NaN。
  2. run：官方两步推理（subprocess，cwd=T-SCAPE repo）：
       Step A  python mhc_pseudo_matching.py I <input.csv> <input_modified.csv>
               → 过滤到 MHC_classI_pseudo.csv 支持的 allele（不支持的行被去掉）
       Step B  python inference_csv.py --csv_path <input_modified.csv>
               --inf_type pmhc_im_neo --output <output.csv>
       平台：WSL2 + conda env（pytorch-cuda11.8），GPU 推理（RTX4070 8GB，权重 0.53GB 够）。
  3. parse：用 merge_tscape.py 的 _norm_allele 归一逻辑（T-SCAPE 输出 Allele 是缩写型
     A0201≠输入 HLA-A*02:01），按 (peptide, allele_norm) join，回贴每行 bb_idx 的 MT。

产出: scripts/out/phaseB/TSCAPE_101102.csv
      列: bb_idx, MT_TSCAPE
方向: score 0-1，越高越免疫原（>0.5=免疫原；官方原始方向，无翻转，核 merge_tscape.py）。

⚠️ GPU device 不匹配根因 + 修法（2026-06-27 实证，读 inference_csv.py 确认非臆造）:
   inference_csv.py 加载 ckpt 后，pmhc_im_neo 分支只 load_state_dict、**没 model.to(device)**；
   推理 loop 前 device 又被重设为 `cuda if available`，输入 `.to(device)` 上 cuda，但模型仍留 CPU
   → `Expected all tensors cpu vs cuda:0`。故光设 CUDA_VISIBLE_DEVICES 不够，必须让模型也上 cuda。
   修法（纯 device 放置，不改数值）：在 `device = torch.device("cuda" ...)` 行后补
   `model_final = model_final.to(device)`。本脚本 preflight 幂等施打此 patch（ensure_device_patch）。

⚠️ 另需两个官方 bug patch（由 setup_tscape_hpc.sh Step 2+2b 施打，依据 04_LOG Entry T3）：
   ① dropout bug：src/model_fused.py:326 → F.dropout(e, self.dropout, training=self.training)
   ② pmhc_im_neo 推理 bug：inference_csv.py load 分支 + task_dict 各加 pmhc_im_neo/pmhc_im_inf
   本脚本 run 前静态 grep 校验 ①②已打，未打报错停（不裸跑非确定性/崩溃）。
⚠️ T-SCAPE 结果须标注：用官方权重 + 修复官方 inference/device bug 跑（非原版代码）。
⚠️ 许可：T-SCAPE 采用 CC BY-NC-ND 4.0（学术非商用 + 禁止演绎），产物仅限 QuantImmuBench
   内部学术评测（seoklab, Sci Adv 2025, DOI 10.1126/sciadv.adz8759）。

用法（在 WSL2 内跑，路径用 /mnt/d/... 解析）:
    python run_tscape_101102.py \
        [--tscape-dir /root/quantimmu/tools_repos/T-SCAPE] \
        [--tscape-python /root/miniconda3/envs/tscape/bin/python] \
        [--inf-type pmhc_im_neo] [--gpu 0] [--smoke N]
    --smoke N: 只跑前 N 个 unique (peptide, allele) 对（验工具能跑、分数合理），不产正式 CSV。
"""
import argparse
import csv
import math
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "tscape_work"  # 中间 input/modified/output
OUT = ROOT / "scripts" / "out" / "phaseB" / "TSCAPE_101102.csv"

# T-SCAPE repo / conda python 默认值（本地 WSL2，主线实测路径）。
DEFAULT_TSCAPE_DIR = "/root/quantimmu/tools_repos/T-SCAPE"
DEFAULT_TSCAPE_PYTHON = "/root/miniconda3/envs/tscape/bin/python"

MAX_PEPTIDE_LEN = 20   # T-SCAPE MHC-I 支持 ≤20mer（超长跳过置 NaN），与 prep_tscape_input.py 一致

# 订正等位真值（仅用于自校验报告，不参与过滤逻辑）。7 个均已核在 MHC_classI_pseudo.csv 中。
CORRECTED_ALLELES = {
    "101": ["HLA-A*66:01", "HLA-B*40:01", "HLA-B*57:01", "HLA-C*06:02"],
    "102": ["HLA-A*02:01", "HLA-B*35:03", "HLA-B*38:01"],
}

# device patch 锚点 + 补丁行（在 inference_csv.py 把模型搬到和输入同一 device）。
_DEVICE_ANCHOR = '    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")\n'
_DEVICE_FIX = '    model_final = model_final.to(device)\n'


def norm_allele(a: str) -> str:
    """HLA-A*02:01 → A0201（去 HLA-、去 *、去 :），与 merge_tscape.py._norm_allele 一致。"""
    a = str(a).strip()
    if a.upper().startswith("HLA-"):
        a = a[4:]
    elif a.upper().startswith("HLA"):
        a = a[3:]
    return a.replace("*", "").replace(":", "")


def check_patches(tscape_dir: Path) -> None:
    """静态 grep 校验两个官方 bug patch（dropout + pmhc_im_neo）已打，未打报错停。"""
    model_file = tscape_dir / "src" / "model_fused.py"
    infer_file = tscape_dir / "inference_csv.py"
    if not model_file.exists():
        raise SystemExit(f"[FAIL] 找不到 {model_file}（T-SCAPE repo 路径不对，改 --tscape-dir）")
    if not infer_file.exists():
        raise SystemExit(f"[FAIL] 找不到 {infer_file}（T-SCAPE repo 路径不对，改 --tscape-dir）")

    model_src = model_file.read_text(encoding="utf-8", errors="replace")
    infer_src = infer_file.read_text(encoding="utf-8", errors="replace")

    if "F.dropout(e, self.dropout, training=self.training)" not in model_src:
        raise SystemExit(
            f"[FAIL] dropout patch 未施打：{model_file}:326 需含 training=self.training\n"
            "  先跑 HPC/deploy/tscape/setup_tscape_hpc.sh Step 2"
        )
    if "pmhc_im_neo" not in infer_src:
        raise SystemExit(
            f"[FAIL] pmhc_im_neo inference patch 未施打：{infer_file} 缺 pmhc_im_neo 键\n"
            "  先跑 HPC/deploy/tscape/setup_tscape_hpc.sh Step 2b（load 分支+task_dict 加键）"
        )
    print(f"[patch] ✅ dropout + pmhc_im_neo inference patch 均已校验（{tscape_dir}）")


def ensure_device_patch(tscape_dir: Path) -> None:
    """幂等施打 device patch：模型搬到和输入同一 device（修 cpu/cuda 不匹配）。

    pmhc_im_neo 分支只 load_state_dict 没 model.to(device)，而 loop 前 device 重设为 cuda、
    输入 .to(cuda) → 模型留 CPU 报 'Expected all tensors cpu vs cuda:0'。
    修法：在 `device = torch.device("cuda"...)` 行后插入 `model_final = model_final.to(device)`。
    纯 device 放置，不改数值。已打则跳过。
    """
    infer_file = tscape_dir / "inference_csv.py"
    src = infer_file.read_text(encoding="utf-8")
    if _DEVICE_FIX in src:
        print(f"[patch] device patch 已存在，跳过（{infer_file}）")
        return
    n = src.count(_DEVICE_ANCHOR)
    if n != 1:
        raise SystemExit(
            f"[FAIL] device patch 锚点匹配 {n} 次（预期 1）：{infer_file}\n"
            f"  锚点行: {_DEVICE_ANCHOR!r}\n  官方代码可能已变，需人工核对后再改 _DEVICE_ANCHOR"
        )
    bak = infer_file.with_suffix(".py.predevicebak")
    if not bak.exists():
        bak.write_text(src, encoding="utf-8")
    src = src.replace(_DEVICE_ANCHOR, _DEVICE_ANCHOR + _DEVICE_FIX)
    infer_file.write_text(src, encoding="utf-8")
    print(f"[patch] ✅ device patch 施打：{infer_file} 加 model_final.to(device)（备份 {bak.name}）")


def find_pseudo_csv(tscape_dir: Path):
    """在 repo 找 MHC_classI_pseudo.csv，返回 (路径, 支持的归一 allele 集)。"""
    cands = list(tscape_dir.rglob("MHC_classI_pseudo.csv"))
    if not cands:
        return None, None
    pseudo = cands[0]
    supported = set()
    with open(pseudo, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if row:
                supported.add(norm_allele(row[0]))
    return pseudo, supported


def run_two_step(tscape_python, tscape_dir, input_csv, input_modified, output_csv, inf_type, env):
    """官方两步推理：mhc_pseudo_matching（Step A）→ inference_csv（Step B）。cwd=repo，GPU。"""
    cmd_a = [tscape_python, "mhc_pseudo_matching.py", "I", str(input_csv), str(input_modified)]
    print(f"[run] Step A: {' '.join(cmd_a)}")
    ra = subprocess.run(cmd_a, cwd=str(tscape_dir), capture_output=True, text=True, env=env, timeout=1800)
    if ra.returncode != 0:
        raise RuntimeError(f"Step A 失败 rc={ra.returncode}: {ra.stderr[:400]}{ra.stdout[:200]}")
    if not Path(input_modified).exists():
        raise RuntimeError(f"Step A 未产出 {input_modified}: {ra.stdout[-400:]}{ra.stderr[-200:]}")

    cmd_b = [tscape_python, "inference_csv.py", "--csv_path", str(input_modified),
             "--inf_type", inf_type, "--output", str(output_csv)]
    print(f"[run] Step B: {' '.join(cmd_b)}")
    rb = subprocess.run(cmd_b, cwd=str(tscape_dir), capture_output=True, text=True, env=env, timeout=7200)
    if rb.returncode != 0:
        raise RuntimeError(f"Step B 失败 rc={rb.returncode}: {rb.stderr[:400]}{rb.stdout[:200]}")
    if not Path(output_csv).exists():
        raise RuntimeError(f"Step B 未产出 {output_csv}: {rb.stdout[-400:]}{rb.stderr[-200:]}")


def parse_output(output_csv):
    """读 T-SCAPE 输出 → {(peptide_upper, allele_norm): score}（用 merge_tscape.py 同逻辑）。"""
    scores = {}
    with open(output_csv, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = {"Allele", "peptide", "score"} - set(fieldnames)
        if missing:
            raise ValueError(f"T-SCAPE 输出缺列 {missing}，实际列 {fieldnames}（预期 Allele,peptide,score）")
        for row in reader:
            pep = row["peptide"].strip().upper()
            allele = norm_allele(row["Allele"])
            try:
                scores[(pep, allele)] = float(row["score"])
            except (ValueError, TypeError):
                continue
    return scores


def main():
    ap = argparse.ArgumentParser(description="Phase B T-SCAPE 重推理 P101/P102（订正 HLA，MT-only，GPU）")
    ap.add_argument("--tscape-dir", default=DEFAULT_TSCAPE_DIR, help="T-SCAPE repo 路径（含 inference_csv.py）")
    ap.add_argument("--tscape-python", default=DEFAULT_TSCAPE_PYTHON, help="T-SCAPE conda env 的 python 二进制")
    ap.add_argument("--inf-type", default="pmhc_im_neo", help="推理任务类型（cancer 必须 pmhc_im_neo）")
    ap.add_argument("--gpu", default="0", help="CUDA_VISIBLE_DEVICES 值（默认 0；传空串 '' 强制 CPU）")
    ap.add_argument("--smoke", type=int, default=0, help="只跑前 N 个 (peptide,allele) 对验工具，不产 CSV")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    tscape_dir = Path(args.tscape_dir)
    if not tscape_dir.exists():
        raise SystemExit(f"[FAIL] T-SCAPE repo 不存在: {tscape_dir}（改 --tscape-dir）")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    # GPU：让模型+输入都上 cuda（device patch 已保证模型搬 device）。
    env = dict(os.environ, PYTHONUTF8="1", CUDA_VISIBLE_DEVICES=str(args.gpu))
    print(f"[env] CUDA_VISIBLE_DEVICES={args.gpu!r}（GPU 推理；device patch 保证模型与输入同 device）")

    # ── 校验官方 patch（dropout + im_neo）+ 施打 device patch ────────────────────
    check_patches(tscape_dir)
    ensure_device_patch(tscape_dir)

    # ── 读 backbone，聚合 unique (MT_peptide, allele) 对（MT-only，去重）─────────────
    rows = []
    pair_to_bbidx = defaultdict(list)
    seen_pairs = []
    seen_set = set()
    skipped_long = 0
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            allele = r["HLA_Allele"].strip()
            pep = (r.get("MT_Subpeptide") or "").strip().upper()
            if not pep:
                continue
            if len(pep) > MAX_PEPTIDE_LEN:
                skipped_long += 1
                continue
            pair = (pep, allele)
            pair_to_bbidx[pair].append(r["bb_idx"])
            if pair not in seen_set:
                seen_set.add(pair)
                seen_pairs.append(pair)

    print(f"[prep] backbone={len(rows)} 行 | unique (MT,allele) 对={len(seen_pairs)} "
          f"| 超{MAX_PEPTIDE_LEN}mer 跳过(置NaN)={skipped_long}")

    # ── 自校验：订正等位是否在 pseudo 表（不在则该格 T-SCAPE 会过滤→NaN）──────────
    pseudo_path, supported = find_pseudo_csv(tscape_dir)
    if supported is None:
        print(f"[selfcheck] ⚠️ 未找到 MHC_classI_pseudo.csv（{tscape_dir} 下），跳过 allele 预检；实际以 Step A 为准")
    else:
        print(f"[selfcheck] pseudo 表 = {pseudo_path}（{len(supported)} 个支持 allele）")
        for pid, alleles in CORRECTED_ALLELES.items():
            for a in alleles:
                tag = "✅在表" if norm_allele(a) in supported else "❌不在表→该格NaN"
                print(f"[selfcheck]   P{pid} {a:<14} ({norm_allele(a):<6}) {tag}")

    # ── 写官方 pmhc_im 输入 CSV（列名 Allele,peptide——peptide 列名小写；值原样大写）──
    run_pairs = seen_pairs[:args.smoke] if args.smoke else seen_pairs
    input_csv = WORKDIR / "tscape_input_101102.csv"
    input_modified = WORKDIR / "tscape_input_101102_modified.csv"
    output_csv = WORKDIR / "tscape_output_101102.csv"
    with open(input_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Allele", "peptide"])  # 官方 pmhc_im 输入列名（peptide 小写，核 example/inputs/pmhc_im.csv）
        for (pep, allele) in run_pairs:
            w.writerow([allele, pep])
    print(f"[prep] 写 T-SCAPE 输入 {input_csv}（{len(run_pairs)} 对）")

    # ── 两步推理 ───────────────────────────────────────────────────────────────
    run_two_step(args.tscape_python, tscape_dir, input_csv, input_modified, output_csv, args.inf_type, env)
    score_dict = parse_output(output_csv)
    smin = min(score_dict.values()) if score_dict else float("nan")
    smax = max(score_dict.values()) if score_dict else float("nan")
    print(f"[run] T-SCAPE 输出 {len(score_dict)} 个 (peptide,allele) 对有分 "
          f"| range [{smin:.4f}, {smax:.4f}] | {len(run_pairs) - len(score_dict)} 对被 pseudo 过滤(NaN)")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(run_pairs)} 个对，工具可跑、分数在合理区间。未产 CSV。")
        return

    # ── 回贴 bb_idx，写 TSCAPE_101102.csv（列 bb_idx, MT_TSCAPE）──────────────────
    def fmt(pep, allele):
        if not pep or len(pep) > MAX_PEPTIDE_LEN:
            return ""  # 空 / 超长未送工具 → NaN
        v = score_dict.get((pep, norm_allele(allele)))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # allele 被过滤 / 未命中 → NaN
        return f"{v:.6f}"

    n_mt = n_mt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_TSCAPE"])
        w.writeheader()
        for r in rows:
            allele = r["HLA_Allele"].strip()
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, allele)
            n_mt += mt_s != ""
            n_mt_nan += mt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_TSCAPE": mt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_TSCAPE: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   方向：score 越高越免疫原（0-1，>0.5=免疫原，无翻转）")


if __name__ == "__main__":
    main()
