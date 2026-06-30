#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0f_freeze_provenance.py
服务: quantimmu-bench / Phase 0 数据地基重建 (03_EXPERIMENT_PLAN.md §3)

冻结 Phase 0 全部产物的 provenance (来源指纹), 防地基漂移。

================== 输入 ==================
  data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx (官方真源)
  data/frozen/*.csv (p0a..p0e 产物)

================== 输出 ==================
  data/frozen/PROVENANCE.json
    - official_xlsx: {path, sha256, n_in_vitro_rows}
    - frozen_files: {<name>: {sha256, n_rows, exists}}
    - tool_versions: TODO 占位 (待 researcher 确认各工具版本/commit)
    - hla_conversion_rule: 文本说明
    - reuse_summary: {reuse, rerun_full, rerun_partial}
    - generated_at: 脚本运行北京时间戳

================== 校验门 ==================
  [P0-f1] 官方 xlsx sha256 非空
  [P0-f2] 所有必需 frozen csv 存在 (pooled_*.csv 允许 pending)

================== 跑法 ==================
  python analysis/phase0/p0f_freeze_provenance.py
"""

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

OFFICIAL_XLSX = (ROOT / "data" / "OFFICIAL_DO_NOT_TOUCH"
                 / "ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx")
FROZEN_DIR = ROOT / "data" / "frozen"
OUT_JSON = FROZEN_DIR / "PROVENANCE.json"

# 必需 frozen 产物 (p0a..p0c)
REQUIRED_FROZEN = [
    "ds2_official_groundtruth.csv",
    "patient_hla.csv",
    "REUSE_DECISION.csv",
    "RERUN_PEPTIDE_LIST.csv",
    "subpep_hla_expansion.csv",
]
# 可 pending 的产物 (依赖外部补跑)
OPTIONAL_FROZEN = [
    "pooled_peptide_level_30tools.csv",
]

HLA_RULE = (
    "原始 token (如 B5701/A0201/C0602) -> 标准化: 拆 位点字母(A/B/C) + "
    "field1(前段数字) + field2(末 2 位) -> 'HLA-<locus>*<field1:02d>:<field2>'; "
    "仅保留 HLA-I (A/B/C); 去重 (P109 重复 B4402); 空格跳过。"
    "新旧 HLA 仅 P104 DIFF (新 A3001=HLA-A*30:01 vs 旧 A0301=HLA-A*03:01)。"
)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def count_rows(path):
    try:
        return int(len(pd.read_csv(path)))
    except Exception as e:        # noqa: BLE001
        return f"ERR:{e}"


def main():
    bj = timezone(timedelta(hours=8))   # 北京时间
    now = datetime.now(bj).isoformat()

    prov = {
        "schema": "quantimmu_phase0_provenance_v1",
        "generated_at": now,
        "project_root": str(ROOT),
    }

    # ── 官方 xlsx ─────────────────────────────────────────────────────────
    if not OFFICIAL_XLSX.exists():
        raise SystemExit(f"[ERR] 官方 xlsx 不存在: {OFFICIAL_XLSX}")
    off_sha = sha256_of(OFFICIAL_XLSX)
    try:
        n_iv = int(len(pd.read_excel(OFFICIAL_XLSX, sheet_name="In Vitro",
                                     engine="openpyxl")))
    except Exception as e:        # noqa: BLE001
        n_iv = f"ERR:{e}"
    prov["official_xlsx"] = {
        "path": str(OFFICIAL_XLSX),
        "sha256": off_sha,
        "n_in_vitro_rows": n_iv,
        "note": "OFFICIAL_DO_NOT_TOUCH 唯一准则数据, 只读",
    }

    # ── frozen 文件指纹 ──────────────────────────────────────────────────
    frozen_files = {}
    missing_required = []
    for name in REQUIRED_FROZEN + OPTIONAL_FROZEN:
        p = FROZEN_DIR / name
        if p.exists():
            frozen_files[name] = {
                "sha256": sha256_of(p),
                "n_rows": count_rows(p),
                "exists": True,
            }
        else:
            frozen_files[name] = {"sha256": None, "n_rows": None, "exists": False}
            if name in REQUIRED_FROZEN:
                missing_required.append(name)
            else:
                frozen_files[name]["status"] = "pending (依赖外部补跑, 见 p0e 依赖说明)"
    prov["frozen_files"] = frozen_files

    # ── reuse 摘要 ───────────────────────────────────────────────────────
    dec_path = FROZEN_DIR / "REUSE_DECISION.csv"
    if dec_path.exists():
        dec = pd.read_csv(dec_path)
        prov["reuse_summary"] = {
            k: int((dec["status"] == k).sum())
            for k in ("reuse", "rerun_full", "rerun_partial")
        }
    else:
        prov["reuse_summary"] = None

    # ── 工具版本 (TODO 占位) ─────────────────────────────────────────────
    prov["tool_versions"] = {
        "__TODO__": ("未找到官方版本号占位 -- 需 researcher 确认 30 工具各自 "
                     "git commit / release version / 模型权重哈希, 逐工具填入此字典"),
    }

    prov["hla_conversion_rule"] = HLA_RULE

    # ── 校验门 ────────────────────────────────────────────────────────────
    assert off_sha, "[P0-f1] FAIL: 官方 xlsx sha256 为空"
    print(f"[P0-f1] PASS: 官方 xlsx sha256 = {off_sha[:16]}...")

    assert not missing_required, (
        f"[P0-f2] FAIL: 必需 frozen csv 缺失: {missing_required}\n"
        f"        先按跑序产齐 (p0a->p0b->p0_reuse->p0c)")
    print(f"[P0-f2] PASS: {len(REQUIRED_FROZEN)} 必需 frozen csv 全存在")
    pending = [n for n in OPTIONAL_FROZEN if not (FROZEN_DIR / n).exists()]
    if pending:
        print(f"[info] pending (依赖外部补跑): {pending}")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(prov, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {OUT_JSON}")
    print("[DONE] p0f_freeze_provenance 完成")


if __name__ == "__main__":
    main()
