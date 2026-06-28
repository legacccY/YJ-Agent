# -*- coding: utf-8 -*-
"""
run_improve_101102.py — Phase B：本地 WSL 版 IMPROVE 101/102 重推理 orchestrator。

为什么本地跑（不上 HPC）：HPC improve env = pandas 2.x（py3.11），原 feature_calc 老代码
不兼容会崩；本地 WSL improve env = pandas 1.3.5（原 86 肽就在这跑的，兼容）。

口径与原 86 肽严格一致（源 = scripts/improve/run_feature_calc.sh + feature_calc_local.py）：
  - netMHCpan-4.1 mut/wt binding ✅
  - PRIME + MixMHCpred ✅
  - SelfSim（内部 blosum62 kernel）✅
  - 理化特征 ✅
  - **netMHCstabpan 仍跳过** → Stability=NaN → Predict fillna(col.mean()) impute。
    ⚠️ 即使本地 wave3 有 netMHCstabpan-1.0 二进制，也**不算 Stability**：原 86 肽
    Stability 全是 NaN(imputed)，若 101/102 算真值则两批喂 RF 的特征分布不一致、
    mean_prediction_rf 不可比 → 破坏「严格一致」。复用 feature_calc_local.py(no-stab 版)。
  - 模型 = Simple，关键列 mean_prediction_rf（越高越强，不翻转）。

env 分工（原 run_feature_calc.sh 一致，两 env）：
  - feature_calc → improve     (pandas 1.3.5，跑老 IMPROVE 代码)
  - Predict      → improve_new  (numpy 2.x，pkl 是 numpy2.x retrained，老 env 报 numpy._core)

外部工具：本地 /root/quantimmu_wave3/{netMHCpan-4.1,netMHCstabpan-1.0,PRIME,MixMHCpred-master}
  （netMHCstabpan 在但不用，见上）。

【主线 WSL 跑法（sudo，本窗不跑）】
  确认 backbone 在 scripts/out/phaseB/backbone_101102.csv 后：
    sudo /root/miniconda3/envs/improve/bin/python \
        /mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/phaseB/run_improve_101102.py
  （orchestrator 用 csv/json 不依赖 pandas，任何 env python 都能起；feature_calc/Predict
   各自走下面 PY_FEATURE/PY_PREDICT 指定的 env。）
  → 产出 scripts/out/phaseB/IMPROVE_101102.csv（列 bb_idx, MT_IMPROVE_mean_prediction_rf）

⚠️ 下面 CONFIG 的 WSL 路径主线跑前先 `ls` 确认（IMPROVE_HOME / 两 env / wave3 子目录名）。

服务: quantimmu-bench Phase B IMPROVE 101/102 重推理（lever=IMPROVE）。
"""
import os
import sys
import csv
import json
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# CONFIG —— 主线跑前先 ls 核实这些 WSL 路径
# ============================================================
# 仓库根（本脚本在 scripts/phaseB/ 下，WSL 里是 /mnt/d/.../QuantImmuBench）
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# conda env python（两 env，口径同原 run_feature_calc.sh）
PY_FEATURE = "/root/miniconda3/envs/improve/bin/python"      # pandas 1.3.5
PY_PREDICT = "/root/miniconda3/envs/improve_new/bin/python"  # numpy 2.x（pkl 兼容）
# ⚠️ 若本地无 improve_new env，Predict pkl(numpy2.x retrained)在 pandas1.3.5 老 env 会报
#    `No module named numpy._core`（见 TOOLS/IMPROVE.md）。届时主线建 improve_new 或核实可用 env。

# IMPROVE 仓库（含 bin/src、models.zip、Predict_*_CLEAN_retrain.py、data/matrices/blosum62.qij）
IMPROVE_HOME = "/root/quantimmu/tools_repos/IMPROVE_tool"    # ⚠️ ls 确认，可能在别处

# 外部工具根（team-lead 给）
WAVE3 = "/root/quantimmu"
NETMHCPAN_41 = "/root/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan"
PRIME_DIR    = "/root/quantimmu/tools_repos/PRIME"
MIXMHC_DIR   = "/root/quantimmu/tools_repos/MixMHCpred"

# IMPROVE 代码期待的 ProgramDir 布局（symlink 适配，与原 run_feature_calc.sh Step0 一致）
PROG_DIR = "/root/quantimmu/improve_programs"

# 口径核心：no-stab 降级版 feature_calc（仓库内，单一真源）
FEATURE_CALC_PY = os.path.join(REPO, "scripts", "improve", "feature_calc_local.py")

# 输入/输出（/mnt/d 仓库内）
BACKBONE  = os.path.join(REPO, "scripts", "out", "phaseB", "backbone_101102.csv")
WORK      = "/tmp/improve_phaseB_work"  # 原生 WSL ext4，避 /mnt/d drvfs 海量小文件 I/O 奇慢（PRIME.x 卡死根因）
FINAL_OUT = os.path.join(REPO, "scripts", "out", "phaseB", "IMPROVE_101102.csv")

DATASET_NAME = "elispot"
OUT_COL = "MT_IMPROVE_mean_prediction_rf"


def norm_hla(s):
    """HLA-A*66:01 -> HLA-A66:01（去星号，与原 improve_input 无星号格式一致）。"""
    return str(s).replace("*", "").strip()


def run(cmd, **kw):
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True, **kw)


# ============================================================
# Step 0: 环境/工具 symlink 准备（与原 run_feature_calc.sh Step0 一致）
# ============================================================
def prepare_programdir():
    os.makedirs(os.path.join(PROG_DIR, "netMHCpan-4.1"), exist_ok=True)
    # netMHCpan-4.1: 代码期待小写 netmhcpan
    link = os.path.join(PROG_DIR, "netMHCpan-4.1", "netmhcpan")
    if not os.path.lexists(link):
        os.symlink(NETMHCPAN_41, link)
    # PRIME / MixMHCpred-master：整目录 symlink
    for name, src in [("PRIME", PRIME_DIR), ("MixMHCpred-master", MIXMHC_DIR)]:
        dst = os.path.join(PROG_DIR, name)
        if not os.path.lexists(dst):
            os.symlink(src, dst)
    print(f"[Step0] ProgramDir 就绪: {PROG_DIR}")


def ensure_predict_local():
    """生成 predict_local.py（base_dir 指向本地 IMPROVE_HOME），与 hpc_improve.sh sed 一致。"""
    predict_local = os.path.join(IMPROVE_HOME, "predict_local.py")
    if os.path.exists(predict_local):
        return predict_local
    src = os.path.join(IMPROVE_HOME, "Predict_immunogenicity_CLEAN_retrain.py")
    with open(src, encoding="utf-8") as f:
        lines = f.readlines()
    with open(predict_local, "w", encoding="utf-8") as f:
        for ln in lines:
            if ln.startswith("base_dir = "):
                f.write(f'base_dir = "{IMPROVE_HOME}"\n')
            else:
                f.write(ln)
    print(f"[Step0] 生成 predict_local.py（base_dir -> {IMPROVE_HOME}）")
    return predict_local


# ============================================================
# Step 1: prep —— backbone -> IMPROVE 输入 + (mut|wt|hla)->bb_idx 映射
# ============================================================
def prep():
    rows = []
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    print(f"[Step1] 读 backbone {len(rows)} 行 <- {BACKBONE}")

    key2bb, seen, n_lenskip = {}, [], 0
    for r in rows:
        mut = str(r["MT_Subpeptide"]).strip()
        norm = str(r["WT_Subpeptide"]).strip()
        hla = norm_hla(r["HLA_Allele"])
        bb = str(r["bb_idx"]).strip()
        if not (8 <= len(mut) <= 12):  # IMPROVE/netMHCpan 适用区间
            n_lenskip += 1
            continue
        key = f"{mut}|{norm}|{hla}"
        if key not in key2bb:
            key2bb[key] = []
            seen.append((mut, norm, hla))
        key2bb[key].append(bb)

    os.makedirs(WORK, exist_ok=True)
    input_tsv = os.path.join(WORK, "improve_input.tsv")
    map_csv = os.path.join(WORK, "improve_input_map.csv")
    # 直接写 Norm_peptide + Patient 列（= 原 run_feature_calc.sh Step1 prepped 的列集）
    with open(input_tsv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["Mut_peptide", "Norm_peptide", "HLA_allele", "Patient"])
        for mut, norm, hla in seen:
            w.writerow([mut, norm, hla, DATASET_NAME])
    with open(map_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "bb_indices"])
        for key, bbs in key2bb.items():
            w.writerow([key, json.dumps(bbs)])

    n_bb = sum(len(v) for v in key2bb.values())
    print(f"[Step1] 去重输入行={len(seen)} | 覆盖 bb_idx={n_bb} | 长度门跳过(非8-12mer)={n_lenskip}")
    for mut, norm, hla in seen[:3]:
        print(f"        {mut}\t{norm}\t{hla}")
    return input_tsv, map_csv


# ============================================================
# Step 2/3: feature_calc（improve env）+ Predict（improve_new env）
# ============================================================
def feature_calc(input_tsv):
    pred_dir = os.path.join(WORK, "predictions")
    features_out = os.path.join(WORK, "calculated_features.tsv")
    for sub in ["netmhcpan41/mut", "netmhcpan41/wt", "netmhcstabpan", "PRIME"]:
        os.makedirs(os.path.join(pred_dir, sub), exist_ok=True)
    env = dict(os.environ)
    env["IMPROVE_SRC"] = os.path.join(IMPROVE_HOME, "bin", "src")  # HPC/本地通用 src 覆盖
    # ⚠️ 真根因修复（2026-06-28）：MixMHCpred wrapper 内部调 `python3`（PATH 解析，见
    #   MixMHCpred 第 171 行 `python3 .../code/main.py`）。orchestrator 用 envs/improve/bin/python
    #   起脚本但【没 conda activate】→ 子进程 PATH 无 improve/bin → python3=/usr/bin/python3
    #   (无 numpy) → MixMHCpred `import numpy` 崩 → 产空 temp 文件 → PRIME.x lib/PRIME.cc 的
    #   `while(!file.eof())` 读空文件 eofbit 永不置 → 99% CPU 死循环、输出 0 字节、几十分钟不返回。
    #   （此前误诊为「DTN 限流 / gpfs I/O / 毒肽」全错；原 86 肽侥幸没踩是因当时跑法 PATH 正确。）
    # 修：把 improve env 的 bin 注入 PATH → MixHCpred 的 python3 解析到 improve python3(带 numpy)。
    improve_bin = os.path.dirname(PY_FEATURE)  # /root/miniconda3/envs/improve/bin
    env["PATH"] = improve_bin + os.pathsep + env.get("PATH", "")
    print("[Step2] feature_calc_local.py（no-stab 降级，与原 86 肽同口径）")
    run([PY_FEATURE, FEATURE_CALC_PY,
         "--file", input_tsv,
         "--dataset", DATASET_NAME,
         "--PredDir", pred_dir,
         "--ProgramDir", PROG_DIR,
         "--TmpDir", PROG_DIR,
         "--outfile", features_out],
        cwd=IMPROVE_HOME, env=env)  # cwd=IMPROVE_HOME → kernelSim 找 data/matrices/blosum62.qij
    return features_out


def predict(features_out, predict_local):
    out = os.path.join(WORK, "improve_simple_101102.tsv")
    print("[Step3] Predict Simple（improve_new env）")
    run([PY_PREDICT, predict_local,
         "--file", features_out, "--model", "Simple", "--outfile", out])
    return out


# ============================================================
# Step 4: parse —— Predict 输出 -> bb_idx 对齐合表列
# ============================================================
def parse(pred_tsv, map_csv):
    key2bb = {}
    with open(map_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key2bb[r["key"]] = json.loads(r["bb_indices"])

    bb2score, n_pred, n_nokey = {}, 0, 0
    with open(pred_tsv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            mut = str(r.get("Mut_peptide", "")).strip()
            norm = str(r.get("Norm_peptide", "")).strip()
            hla = norm_hla(r.get("HLA_allele", ""))
            val = r.get("mean_prediction_rf", "")
            if val in ("", "nan", "NaN", None):
                continue
            n_pred += 1
            bbs = key2bb.get(f"{mut}|{norm}|{hla}")
            if bbs is None:
                n_nokey += 1
                continue
            for bb in bbs:
                bb2score[bb] = val

    with open(FINAL_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bb_idx", OUT_COL])
        for bb, val in bb2score.items():
            w.writerow([bb, val])
    print(f"[Step4] Predict 有效行={n_pred} | 未匹配键={n_nokey} | 回填 bb_idx={len(bb2score)}")
    print(f"[Step4] 写 {FINAL_OUT}（列 bb_idx, {OUT_COL}）")
    for bb, val in list(bb2score.items())[:3]:
        print(f"        bb_idx={bb}\t{OUT_COL}={val}")


def main():
    prepare_programdir()
    predict_local = ensure_predict_local()
    input_tsv, map_csv = prep()
    features_out = feature_calc(input_tsv)
    pred_tsv = predict(features_out, predict_local)
    parse(pred_tsv, map_csv)
    print("\n===== IMPROVE 101/102 (本地 WSL) DONE =====")
    print(f"合表列: {FINAL_OUT}  (bb_idx, {OUT_COL})")
    print("口径: netMHCpan-4.1 + PRIME/MixMHCpred + SelfSim，跳 stabpan(Stability=NaN)，Simple（与原 86 肽一致）")


if __name__ == "__main__":
    main()
