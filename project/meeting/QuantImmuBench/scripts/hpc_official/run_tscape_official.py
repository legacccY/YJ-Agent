# -*- coding: utf-8 -*-
"""run_tscape_official.py — T-SCAPE 官方 neoantigen 免疫原性预测 orchestrator。
服务 quantimmu-bench / Conductor 节点 tools_dtu / lever=6 工具补跑舰队（补 T-SCAPE，
tools_dtu 最后 1 个免疫原性工具）。T-SCAPE 非 DTU 工具，但同属本节点补跑批次。

★ 本脚本只做 IO 适配 + shell out 官方脚本，算法零改（复现零偏离）。我（coder）不跑，主线跑。

================================================================================
T-SCAPE = seoklab/T-SCAPE（https://github.com/seoklab/T-SCAPE，Science Advances 2025）。
本任务只用 inf_type = pmhc_im_neo（癌症免疫治疗 neoantigen 免疫原性，单权重，CPU 可跑）。

官方命令序列（README 权威，本脚本逐步 subprocess 调用，cwd=TSCAPE 仓库根）:
  # ① HLA→pseudo 序列映射（class I）。modify_entry_2 内部把 HLA-A*66:01 归一成 A6601 再 merge，
  #    故输入 Allele 保留 WHO 原格式即可，无需我方预转（prep_tscape_official.py 已保留原格式）。
  python mhc_pseudo_matching.py I <tscape_input.csv> <tscape_input_modified.csv>
  # ② 推理（单权重由 inf_type 自动选 best_param/pmhc_im_neo/...bestvalloss.pt；device=cpu）
  python inference_csv.py --csv_path <tscape_input_modified.csv> --inf_type pmhc_im_neo --output <tscape_output.csv>

输出列 = Allele(已被 ① 归一成 A6601), peptide, score。score∈[0,1] 越高越免疫原，不翻向。

================================================================================
主线要执行的完整命令序列（我不跑，主线串行跑）:

  # 0) clone 仓库 + 下单权重 529MB 到 best_param/pmhc_im_neo/
  git clone https://github.com/seoklab/T-SCAPE.git <TSCAPE_DIR>
  mkdir -p <TSCAPE_DIR>/best_param/pmhc_im_neo
  curl -L -o <TSCAPE_DIR>/best_param/pmhc_im_neo/BigMHC_finalMedium_OAS_el-mlm_ADV1.0_bestvalloss.pt \
    https://huggingface.co/seoklab/T-SCAPE/resolve/main/best_param/pmhc_im_neo/BigMHC_finalMedium_OAS_el-mlm_ADV1.0_bestvalloss.pt
  # 官方 env: conda create -n immuno python=3.10; conda install numpy matplotlib scikit-learn pandas wandb pytorch ...

  # 1) 生成 T-SCAPE 输入（读 master_backbone_official.csv → tscape_inputs/tscape_input.csv + map）
  python scripts/hpc_official/prep_tscape_official.py

  # 2) 跑本 orchestrator（① 映射 + ② 推理；产 tscape_inputs/tscape_output.csv）
  python scripts/hpc_official/run_tscape_official.py --tscape-dir <TSCAPE_DIR>
  #   先验算子（最小 2 样本，需权重已下）: python scripts/hpc_official/run_tscape_official.py --tscape-dir <TSCAPE_DIR> --smoke 2

  # 3) parse 回贴 → TSCAPE_official.csv（1761 行对齐）
  python scripts/hpc_official/parse_tscape_official.py

================================================================================
⚠️ RISK（交主线烟测时核实，不臆改 T-SCAPE 源码）:
  repo HEAD 的 inference_csv.py 中 pmhc_im_neo 似既未进任何 state_dict 加载分支、
  底部 task_dict 也只有键 "pmhc_im" 无 "pmhc_im_neo"（task_dict[args.inf_type] 可能 KeyError）。
  但 README（同 commit）明确文档化 --inf_type pmhc_im_neo。复现零偏离=不改其源码：
  若 ② 推理崩 KeyError / 权重未加载 → 停下报主线，escalate researcher 复核版本/commit，不私自打补丁。

Windows：utf-8 explicit + pathlib。本脚本仅标准库 + subprocess，不引 scipy。
依赖运行环境：T-SCAPE 仓库 + 其 conda env（即 sys.executable 须在 immuno env 内或主线显式指定）。
"""
import argparse
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 官方单权重相对路径（相对 TSCAPE 仓库根；由 inf_type=pmhc_im_neo 自动选，这里仅做存在性预检）
WEIGHT_REL = "best_param/pmhc_im_neo/BigMHC_finalMedium_OAS_el-mlm_ADV1.0_bestvalloss.pt"
WEIGHT_URL = ("https://huggingface.co/seoklab/T-SCAPE/resolve/main/"
              "best_param/pmhc_im_neo/BigMHC_finalMedium_OAS_el-mlm_ADV1.0_bestvalloss.pt")


def _need(p: Path, what: str, hint: str = "") -> None:
    if not p.exists():
        print(f"[FATAL] 缺 {what}: {p}" + (f"\n        {hint}" if hint else ""), file=sys.stderr)
        sys.exit(2)


def main():
    script_dir = Path(__file__).resolve().parent                 # scripts/hpc_official
    out_dir = script_dir.parent / "out_official" / "tscape_inputs"
    default_input = out_dir / "tscape_input.csv"
    default_output = out_dir / "tscape_output.csv"

    ap = argparse.ArgumentParser(description="T-SCAPE 官方推理 orchestrator（pmhc_im_neo）")
    ap.add_argument("--tscape-dir", required=True,
                    help="T-SCAPE 仓库克隆根目录（含 inference_csv.py / mhc_pseudo_matching.py / MHC_classI_pseudo.csv）")
    ap.add_argument("--input", default=str(default_input),
                    help="prep_tscape_official.py 产的 tscape_input.csv（列 Allele,peptide）")
    ap.add_argument("--output", default=str(default_output),
                    help="T-SCAPE 推理输出 CSV（列 Allele,peptide,score）→ 供 parse_tscape_official.py")
    ap.add_argument("--inf-type", default="pmhc_im_neo",
                    help="官方 inf_type（本任务固定 pmhc_im_neo，勿改——复现零偏离）")
    ap.add_argument("--mhc-class", default="I", choices=["I", "II"],
                    help="MHC class（neoantigen class I）")
    ap.add_argument("--python", default=sys.executable,
                    help="跑官方脚本用的 python（须在 T-SCAPE conda env 内；default=当前解释器）")
    ap.add_argument("--smoke", type=int, default=0,
                    help=">0 时只取前 N 个 (Allele,peptide) 对做最小验算子（需权重已下）")
    a = ap.parse_args()

    repo = Path(a.tscape_dir).resolve()
    infer_py = repo / "inference_csv.py"
    match_py = repo / "mhc_pseudo_matching.py"
    pseudo_csv = repo / ("MHC_classI_pseudo.csv" if a.mhc_class == "I" else "MHC_classII_pseudo.csv")
    weight = repo / WEIGHT_REL

    # ---- 预检（缺即 FATAL，给主线明确补救指令，不静默造数）----
    _need(repo, "T-SCAPE 仓库根", "git clone https://github.com/seoklab/T-SCAPE.git <TSCAPE_DIR>")
    _need(infer_py, "inference_csv.py")
    _need(match_py, "mhc_pseudo_matching.py")
    _need(pseudo_csv, f"MHC_class{a.mhc_class}_pseudo.csv")
    _need(weight, "单权重 .pt（529MB）", f"curl -L -o {weight} {WEIGHT_URL}")

    in_path = Path(a.input).resolve()
    _need(in_path, "tscape_input.csv", "先跑 python scripts/hpc_official/prep_tscape_official.py")

    out_path = Path(a.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # smoke：截前 N 行另存（不动原 input）
    work_input = in_path
    if a.smoke and a.smoke > 0:
        import csv
        smoke_in = out_path.parent / "tscape_input_smoke.csv"
        with open(in_path, newline="", encoding="utf-8") as fi, \
             open(smoke_in, "w", newline="", encoding="utf-8") as fo:
            rd = csv.reader(fi)
            wr = csv.writer(fo)
            header = next(rd)
            wr.writerow(header)
            for i, row in enumerate(rd):
                if i >= a.smoke:
                    break
                wr.writerow(row)
        work_input = smoke_in
        print(f"[smoke] 仅取前 {a.smoke} 对 → {work_input}", flush=True)

    modified = out_path.parent / "tscape_input_modified.csv"

    # ---- ① HLA→pseudo 映射（官方 mhc_pseudo_matching.py，算法不改）----
    cmd1 = [a.python, str(match_py), a.mhc_class, str(work_input), str(modified)]
    print(f"[step1] cwd={repo} :: {' '.join(cmd1)}", flush=True)
    r1 = subprocess.run(cmd1, cwd=str(repo))
    if r1.returncode != 0 or not modified.exists():
        print(f"[FATAL] mhc_pseudo_matching 失败 rc={r1.returncode}（modified 未生成）", file=sys.stderr)
        sys.exit(3)

    # ---- ② 推理（官方 inference_csv.py，单权重由 inf_type 自动选；device=cpu）----
    cmd2 = [a.python, str(infer_py),
            "--csv_path", str(modified),
            "--inf_type", a.inf_type,
            "--output", str(out_path)]
    print(f"[step2] cwd={repo} :: {' '.join(cmd2)}", flush=True)
    r2 = subprocess.run(cmd2, cwd=str(repo))
    if r2.returncode != 0 or not out_path.exists():
        print(f"[FATAL] inference_csv 失败 rc={r2.returncode}（output 未生成）。"
              f"若 KeyError 'pmhc_im_neo' / 权重未加载 → 见本脚本顶部 RISK，停下报主线 escalate researcher。",
              file=sys.stderr)
        sys.exit(4)

    # 行数提示（不解析内容，留给 parse_tscape_official.py 精确回贴）
    try:
        n_out = sum(1 for _ in open(out_path, encoding="utf-8")) - 1
    except Exception:
        n_out = -1
    print(f"[OUT] {out_path}  数据行≈{n_out}（列 Allele,peptide,score）", flush=True)
    print("[next] 跑 parse: python scripts/hpc_official/parse_tscape_official.py "
          f"--tscape-out {out_path}", flush=True)


if __name__ == "__main__":
    main()
