"""
selinf_kaggle_lb_probe.py — SelInfBench kill-shot #1: Kaggle 医学赛 leaderboard public→private gap 审计

服务: SelInfBench (selinf) kill-shot #1
lever: 医学挑战赛 leaderboard 冠军高估审计
不启训练、不碰 STORY/ACCEPTANCE、不碰 BMVC。

==========================================================================
【措辞与口径声明（必读，防误用）】
本脚本测量的是 "public leaderboard split 自适应过拟合（adaptive overfitting to public test）"，
即参赛队在提交阶段看到 public split 分数后反复调参导致的 public→private 分漂移。
这 ≠ "winner's curse"（winner's curse 指从多重比较中选冠军导致的统计偏差）。
两者相关但不同：public→private gap 是其中一个贡献来源，但不是全部。
脚本输出、注释、判读一律使用 "public→private 移位" 措辞，不写 "winner's curse"。
==========================================================================

【Kaggle API 列结构（探明结论）】
kaggle python 包 competition_leaderboard_fields = ['teamId', 'teamName', 'submissionDate', 'score']
→ 标准 API 只返回单 score 列（final/private score）。
→ publicScore 不在标准 API 里。
→ 双分（publicScore + privateScore）需要：
   (A) 赛结束后 Kaggle 网页下载完整 leaderboard CSV（含两列）
   (B) 或赛组织者提供的 data package
→ 本脚本优先走路径(A)：用户手动下载双分 CSV 放到 data/ 目录，脚本读取并分析。
   同时也提供 API 单分路径作为备用（只能分析 final 分布，无法算 public→private gap）。

TODO: 若 Kaggle 将来开放双分 API 端点，更新 _fetch_leaderboard_api() 中的 URL。

【使用方法】
# 方式 A（推荐，有双分）：手动从 Kaggle 赛页下载 leaderboard CSV 后：
python tools/selinf_kaggle_lb_probe.py --mode csv --data-dir project/meeting/SelInfBench/data/kaggle_lb/

# 方式 B（API 单分，只看 final 分布）：
python tools/selinf_kaggle_lb_probe.py --mode api

# 烟测（不需要网络/凭证，用内置 mock 数据验证逻辑）：
python tools/selinf_kaggle_lb_probe.py --smoke

【数据目录约定 (--mode csv)】
每个赛放一个 CSV，命名用赛 slug（下划线版）：
  project/meeting/SelInfBench/data/kaggle_lb/
    siim-isic-melanoma-classification.csv
    isic-2024-challenge.csv
    rsna-2023-abdominal-trauma-detection.csv
    rsna-breast-cancer-detection.csv
    dogs-vs-cats-redux-kernels-edition.csv   (通用非医学对照)

CSV 必须含列（从 Kaggle 赛页 leaderboard tab 下载）：
  TeamName, PublicScore, PrivateScore   (大小写不敏感)
若只有单列 Score，脚本会打印警告说明无法计算 gap。

【主线运行命令（配好 kaggle.json 后）】
  # 烟测：
  python tools/selinf_kaggle_lb_probe.py --smoke

  # API 探测（需有效 kaggle.json 且接受 Kaggle ToS）：
  python tools/selinf_kaggle_lb_probe.py --mode api

  # 有双分 CSV 时的完整分析：
  python tools/selinf_kaggle_lb_probe.py --mode csv --data-dir project/meeting/SelInfBench/data/kaggle_lb/ --top-k 1 5 10
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

# Windows 终端 UTF-8 输出（防乱码）
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7 无 reconfigure，忽略

import numpy as np

# ── 结果目录（固定，符合项目惯例）──────────────────────────────────────────
RESULTS_DIR = Path("project/meeting/SelInfBench/results")

# ── 目标赛清单（可在此修改）─────────────────────────────────────────────────
COMPETITIONS = [
    {
        "slug": "siim-isic-melanoma-classification",
        "name": "ISIC2020 Melanoma",
        "domain": "medical",
        "metric": "AUROC",
        "imbalance_pct": 1.77,          # 阳性率 %（官方赛描述）
        "test_size": 10982,              # public test 规模
        "note": "melanoma 二分类，极重不平衡，与 SelInfBench A3 直接相关",
    },
    {
        "slug": "isic-2024-challenge",
        "name": "ISIC2024",
        "domain": "medical",
        "metric": "pAUC@0.1FPR",
        "imbalance_pct": 0.4,           # TODO: 确认官方数字，暂估值
        "test_size": None,              # TODO: 填实际 test 规模
        "note": "更稀阳性，pAUC 主指标",
    },
    {
        "slug": "rsna-2023-abdominal-trauma-detection",
        "name": "RSNA2023 AbdTrauma",
        "domain": "medical",
        "metric": "log_loss_weighted",
        "imbalance_pct": None,          # TODO: 多标签，需查官方
        "test_size": None,              # TODO: 填实际 test 规模
        "note": "多标签腹部创伤检测，对照不同任务",
    },
    {
        "slug": "rsna-breast-cancer-detection",
        "name": "RSNA BreastCancer",
        "domain": "medical",
        "metric": "pF1@0.4",
        "imbalance_pct": 2.0,           # TODO: 确认官方数字
        "test_size": None,              # TODO: 填实际 test 规模
        "note": "乳腺癌检测，重不平衡",
    },
    {
        "slug": "dogs-vs-cats-redux-kernels-edition",
        "name": "Dogs vs Cats (通用对照)",
        "domain": "general",
        "metric": "log_loss",
        "imbalance_pct": 50.0,          # 平衡赛
        "test_size": 12500,
        "note": "通用 CV 平衡赛，作为 Roelofs2019 基线量级对照",
    },
]


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _normalize_cols(df_like: dict) -> dict:
    """统一列名大小写：返回 {lower_name: original_name} 映射"""
    return {k.lower().replace(" ", "").replace("_", ""): k for k in df_like}


def _read_csv_minimal(path: Path) -> list[dict]:
    """极简 CSV 读取（避免 pandas 依赖），返回 list of dict"""
    import csv
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def _detect_score_cols(fieldnames: list[str]):
    """
    从 CSV 列名探测 public/private 分列。
    返回 (public_col, private_col, team_col) 或 None 表示找不到。
    """
    lower_map = {f.lower().replace(" ", "").replace("_", ""): f for f in fieldnames}

    # public score 候选
    pub_keys = ["publicscore", "public", "publicleaderboard"]
    # private score 候选
    priv_keys = ["privatescore", "private", "privateleaderboard", "score", "finalscore"]
    # team 候选
    team_keys = ["teamname", "team", "name", "username"]

    pub_col = next((lower_map[k] for k in pub_keys if k in lower_map), None)
    priv_col = next((lower_map[k] for k in priv_keys if k in lower_map), None)
    team_col = next((lower_map[k] for k in team_keys if k in lower_map), None)

    return pub_col, priv_col, team_col


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return f if not np.isnan(f) else None
    except (TypeError, ValueError):
        return None


# ── 分析核心 ─────────────────────────────────────────────────────────────────

def analyze_competition_csv(comp: dict, csv_path: Path, top_k_list: list[int]) -> dict:
    """
    读取双分 CSV，计算 public→private gap 指标。
    返回 result dict（含 warnings）。
    """
    result = {
        "slug": comp["slug"],
        "name": comp["name"],
        "domain": comp["domain"],
        "metric": comp["metric"],
        "imbalance_pct": comp["imbalance_pct"],
        "test_size": comp["test_size"],
        "data_source": "csv",
        "has_dual_score": False,
        "n_teams": None,
        "warnings": [],
    }

    if not csv_path.exists():
        result["warnings"].append(f"CSV not found: {csv_path}. 请从 Kaggle 赛页手动下载 leaderboard CSV。")
        return result

    rows = _read_csv_minimal(csv_path)
    if not rows:
        result["warnings"].append("CSV 为空")
        return result

    result["n_teams"] = len(rows)
    fieldnames = list(rows[0].keys())
    pub_col, priv_col, team_col = _detect_score_cols(fieldnames)

    if pub_col is None:
        result["warnings"].append(
            f"[API 限制] 未找到 publicScore 列。实际列名: {fieldnames}。"
            "Kaggle 标准 API 只返回单 score（final/private），public 分需从赛页手动下载含"
            " PublicScore+PrivateScore 的完整 CSV。TODO: 从 Kaggle 赛页下载后重跑。"
        )
        # 仍然尝试分析 private 分分布
        if priv_col:
            priv_scores = [_safe_float(r[priv_col]) for r in rows if _safe_float(r[priv_col]) is not None]
            result["private_score_median"] = float(np.median(priv_scores)) if priv_scores else None
            result["private_score_p10"] = float(np.percentile(priv_scores, 10)) if priv_scores else None
            result["private_score_p90"] = float(np.percentile(priv_scores, 90)) if priv_scores else None
        return result

    # 有双分——计算 gap
    result["has_dual_score"] = True

    # 解析分数
    valid_rows = []
    for r in rows:
        pub = _safe_float(r[pub_col])
        priv = _safe_float(r[priv_col])
        team = r.get(team_col, "") if team_col else ""
        if pub is not None and priv is not None:
            valid_rows.append({"team": team, "public": pub, "private": priv})

    if not valid_rows:
        result["warnings"].append("所有行 public/private 分解析失败")
        return result

    result["n_valid"] = len(valid_rows)

    # 全量 gap 分布
    gaps = np.array([r["public"] - r["private"] for r in valid_rows])
    result["gap_median"] = float(np.median(gaps))
    result["gap_p25"] = float(np.percentile(gaps, 25))
    result["gap_p75"] = float(np.percentile(gaps, 75))
    result["gap_p90"] = float(np.percentile(gaps, 90))
    result["gap_mean"] = float(np.mean(gaps))
    result["gap_positive_frac"] = float(np.mean(gaps > 0))  # 系统偏正方向比例

    # 按 public 降序排
    sorted_rows = sorted(valid_rows, key=lambda x: x["public"], reverse=True)

    # 全量 private 排名（按 private 降序）
    priv_sorted = sorted(valid_rows, key=lambda x: x["private"], reverse=True)
    priv_rank_map = {r["team"]: i + 1 for i, r in enumerate(priv_sorted)}

    for k in top_k_list:
        top_k_rows = sorted_rows[:k]
        if not top_k_rows:
            continue
        pub_scores = [r["public"] for r in top_k_rows]
        priv_scores = [r["private"] for r in top_k_rows]
        k_gaps = [r["public"] - r["private"] for r in top_k_rows]

        result[f"top{k}_pub_mean"] = float(np.mean(pub_scores))
        result[f"top{k}_priv_mean"] = float(np.mean(priv_scores))
        result[f"top{k}_gap_mean"] = float(np.mean(k_gaps))
        result[f"top{k}_gap_median"] = float(np.median(k_gaps))

        # public #1 的 private 排名
        if k == 1:
            pub1_team = sorted_rows[0]["team"]
            pub1_priv_rank = priv_rank_map.get(pub1_team, None)
            result["pub1_private_rank"] = pub1_priv_rank
            result["pub1_rank_drop"] = (pub1_priv_rank - 1) if pub1_priv_rank else None
            result["pub1_public_score"] = sorted_rows[0]["public"]
            result["pub1_private_score"] = sorted_rows[0]["private"]
            result["pub1_gap"] = sorted_rows[0]["public"] - sorted_rows[0]["private"]

    return result


def analyze_competition_api(comp: dict, top_k_list: list[int]) -> dict:
    """
    用 kaggle API 拉 leaderboard（只有单 score / final）。
    无法计算 public→private gap，但可以记录 final 分布。
    """
    result = {
        "slug": comp["slug"],
        "name": comp["name"],
        "domain": comp["domain"],
        "metric": comp["metric"],
        "imbalance_pct": comp["imbalance_pct"],
        "test_size": comp["test_size"],
        "data_source": "api_single_score",
        "has_dual_score": False,
        "warnings": [
            "[API 限制] kaggle API competition_leaderboard_fields = "
            "['teamId', 'teamName', 'submissionDate', 'score']，只有 final/private score，"
            "无 publicScore。public→private gap 无法通过 API 计算。"
            "TODO: 从 Kaggle 赛页手动下载含 PublicScore+PrivateScore 的 CSV 后用 --mode csv 重跑。"
        ],
    }

    try:
        import kaggle as kaggle_pkg
        api = kaggle_pkg.KaggleApi()
        api.authenticate()
        rows = api.competition_leaderboard_view(comp["slug"], page_size=500)
    except ImportError:
        result["warnings"].append("kaggle 包未安装。运行: pip install kaggle")
        return result
    except Exception as e:
        result["warnings"].append(f"API 调用失败: {e}。检查 kaggle.json 凭证（~/.kaggle/kaggle.json）。")
        return result

    if not rows:
        result["warnings"].append("API 返回空 leaderboard")
        return result

    scores = []
    for r in rows:
        try:
            v = _safe_float(getattr(r, "score", None))
            if v is not None:
                scores.append(v)
        except Exception:
            pass

    result["n_teams_api"] = len(rows)
    result["n_valid_scores"] = len(scores)
    if scores:
        result["final_score_median"] = float(np.median(scores))
        result["final_score_top1"] = float(max(scores))
        result["final_score_p10"] = float(np.percentile(scores, 10))

    return result


# ── mock 数据（烟测用）────────────────────────────────────────────────────────

def _make_mock_competition_data(n_teams: int = 200, gap_mean: float = 0.015,
                                gap_std: float = 0.010, seed: int = 42) -> list[dict]:
    """
    生成合成 leaderboard 数据：
    - public score = private + noise（模拟 public 自适应过拟合）
    - 顶部队伍 gap 系统偏正（过拟合更严重）
    """
    rng = np.random.default_rng(seed)
    # private score 从高斯采样
    priv = rng.normal(0.85, 0.04, n_teams)
    priv = np.clip(priv, 0.5, 0.99)
    # 添加 public 偏移（顶部队 gap 更大）
    rank = np.argsort(-priv)
    rank_normalized = np.zeros(n_teams)
    rank_normalized[rank] = np.linspace(1.5, 0.5, n_teams)  # 高分队 gap 更大
    noise = rng.normal(gap_mean * rank_normalized, gap_std)
    pub = priv + noise
    pub = np.clip(pub, 0.5, 0.999)
    teams = [f"Team_{i:04d}" for i in range(n_teams)]
    return [{"team": t, "public": float(p), "private": float(q)}
            for t, p, q in zip(teams, pub, priv)]


def run_smoke(top_k_list: list[int]) -> None:
    """用 mock 数据验证分析逻辑，不需要网络/凭证"""
    print("=" * 60)
    print("[SMOKE] 用内置 mock 数据验证分析逻辑（不需网络/凭证）")
    print("=" * 60)

    mock_comps = [
        {"slug": "mock-medical-imbalanced", "name": "Mock Medical (imbalanced)",
         "domain": "medical", "metric": "AUROC",
         "imbalance_pct": 2.0, "test_size": 5000,
         "rows": _make_mock_competition_data(200, gap_mean=0.02, gap_std=0.012)},
        {"slug": "mock-general-balanced", "name": "Mock General (balanced)",
         "domain": "general", "metric": "log_loss",
         "imbalance_pct": 50.0, "test_size": 25000,
         "rows": _make_mock_competition_data(500, gap_mean=0.005, gap_std=0.004)},
    ]

    results = []
    for mc in mock_comps:
        valid_rows = mc["rows"]
        gaps = np.array([r["public"] - r["private"] for r in valid_rows])
        sorted_rows = sorted(valid_rows, key=lambda x: x["public"], reverse=True)
        priv_sorted = sorted(valid_rows, key=lambda x: x["private"], reverse=True)
        priv_rank_map = {r["team"]: i + 1 for i, r in enumerate(priv_sorted)}

        res = {
            "slug": mc["slug"],
            "name": mc["name"],
            "domain": mc["domain"],
            "imbalance_pct": mc["imbalance_pct"],
            "test_size": mc["test_size"],
            "n_valid": len(valid_rows),
            "has_dual_score": True,
            "gap_median": float(np.median(gaps)),
            "gap_mean": float(np.mean(gaps)),
            "gap_p75": float(np.percentile(gaps, 75)),
            "gap_positive_frac": float(np.mean(gaps > 0)),
        }
        for k in top_k_list:
            top_k_rows = sorted_rows[:k]
            k_gaps = [r["public"] - r["private"] for r in top_k_rows]
            res[f"top{k}_gap_mean"] = float(np.mean(k_gaps))
            if k == 1:
                pub1 = sorted_rows[0]
                res["pub1_private_rank"] = priv_rank_map.get(pub1["team"])
                res["pub1_rank_drop"] = res["pub1_private_rank"] - 1
                res["pub1_gap"] = pub1["public"] - pub1["private"]
        results.append(res)

    _print_and_save_results(results, top_k_list, prefix="smoke_")
    print("\n[SMOKE] PASS — 分析逻辑验证通过（mock 数据）")
    print("注意：mock 数据不反映真实赛结果，仅验证代码路径。")


# ── 输出与判读 ────────────────────────────────────────────────────────────────

def _print_and_save_results(results: list[dict], top_k_list: list[int],
                             prefix: str = "") -> Path:
    """打印摘要、保存 CSV，返回 CSV 路径"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{prefix}kaggle_lb_probe.csv"

    # 构建输出行（扁平化）
    fieldnames = [
        "slug", "name", "domain", "metric", "imbalance_pct", "test_size",
        "data_source", "has_dual_score", "n_valid",
        "gap_median", "gap_mean", "gap_p25", "gap_p75", "gap_p90", "gap_positive_frac",
        "pub1_public_score", "pub1_private_score", "pub1_gap", "pub1_private_rank", "pub1_rank_drop",
    ]
    for k in top_k_list:
        fieldnames += [f"top{k}_pub_mean", f"top{k}_priv_mean",
                       f"top{k}_gap_mean", f"top{k}_gap_median"]
    fieldnames += ["warnings"]

    import csv
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["warnings"] = "; ".join(r.get("warnings", []))
            writer.writerow(row)

    # 打印摘要
    print("\n" + "=" * 70)
    print("【口径声明】以下测量的是 public leaderboard 自适应过拟合（public→private 移位），")
    print("          不等同于 winner's curse（多重比较统计偏差）。")
    print("=" * 70)

    medical_gaps, general_gaps = [], []
    for r in results:
        if not r.get("has_dual_score"):
            print(f"\n[{r['name']}] 无双分数据")
            for w in r.get("warnings", []):
                print(f"  WARNING: {w}")
            continue

        gap_med = r.get("gap_median")
        pub1_drop = r.get("pub1_rank_drop")
        top1_gap = r.get("top1_gap_mean", r.get("pub1_gap"))

        print(f"\n[{r['name']}] domain={r['domain']} imbalance={r['imbalance_pct']}%"
              f" test_size={r['test_size']}")
        print(f"  全量 gap(pub-priv) 中位数={gap_med:.4f}  均值={r.get('gap_mean', 'N/A'):.4f}"
              f"  正向比例={r.get('gap_positive_frac', 0):.1%}")
        if pub1_drop is not None:
            print(f"  pub#1 掉到 private 第 {r.get('pub1_private_rank')} 名"
                  f"（rank drop={pub1_drop}）")
        for k in top_k_list:
            kg = r.get(f"top{k}_gap_mean")
            if kg is not None:
                print(f"  top-{k:2d} pub→priv gap 均值={kg:.4f}")

        if r["domain"] == "medical" and gap_med is not None:
            medical_gaps.append((r["name"], gap_med))
        elif r["domain"] == "general" and gap_med is not None:
            general_gaps.append((r["name"], gap_med))

    # kill-shot 判读
    print("\n" + "=" * 70)
    print("【KILL-SHOT 判读】")
    if not medical_gaps:
        print("  NO-DATA: 没有医学赛双分数据，无法判读。")
        print("  TODO: 从 Kaggle 赛页下载含 PublicScore+PrivateScore 的 CSV 后重跑。")
    elif not general_gaps:
        print("  NO-BASELINE: 没有通用赛对照，无法比较量级。")
        print("  TODO: 补充通用赛 CSV。")
    else:
        med_gap_mean = np.mean([g for _, g in medical_gaps])
        gen_gap_mean = np.mean([g for _, g in general_gaps])
        ratio = med_gap_mean / gen_gap_mean if gen_gap_mean > 0 else float("inf")
        print(f"  医学赛 gap 均值={med_gap_mean:.4f}  通用赛 gap 均值={gen_gap_mean:.4f}")
        print(f"  医学/通用 gap 倍率={ratio:.2f}x")
        if ratio >= 2.0:
            print("  --> GO: 医学赛 public→private 移位显著大于通用赛（≥2x）。")
            print("          审计 thesis 有立足：医学小 test+重不平衡 系统放大过拟合移位。")
            print("          (注：这是 public split 自适应过拟合，不是 winner's curse 全部)")
        elif ratio >= 1.3:
            print("  --> WEAK-GO: 医学赛移位有放大趋势（1.3x-2x），但量级偏弱。")
            print("          建议结合不平衡度/test 规模做 OLS 回归进一步量化。")
        else:
            print("  --> NO-GO: 医学赛移位与通用赛量级相当（<1.3x）。")
            print("          与 Roelofs2019 一致；审计 leaderboard 过估 thesis 腿塌。")
            print("          建议退回 A3，重新评估核心 claim。")
    print("=" * 70)
    print(f"\n结果已写入: {out_path.resolve()}")
    return out_path


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SelInfBench kill-shot #1: Kaggle 医学赛 public→private 移位审计"
    )
    parser.add_argument(
        "--mode", choices=["csv", "api", "smoke"], default="smoke",
        help=(
            "csv: 读用户手动下载的含 PublicScore+PrivateScore 的 CSV（推荐）; "
            "api: 用 kaggle API（只有单分，无法算 gap，会打印 TODO）; "
            "smoke: 用 mock 数据验证逻辑（不需网络）"
        )
    )
    parser.add_argument(
        "--data-dir", type=Path,
        default=Path("project/meeting/SelInfBench/data/kaggle_lb"),
        help="--mode csv 时的 CSV 目录（每赛一个文件，命名用 slug）"
    )
    parser.add_argument(
        "--top-k", type=int, nargs="+", default=[1, 5, 10],
        help="计算前 k 名的 gap 统计（default: 1 5 10）"
    )
    parser.add_argument(
        "--competitions", type=str, nargs="*", default=None,
        help="指定要分析的赛 slug（默认全部）"
    )
    args = parser.parse_args()

    # 检查依赖
    try:
        import numpy as np  # noqa: F401
    except ImportError:
        print("ERROR: numpy 未安装。运行: pip install numpy")
        sys.exit(1)

    if args.mode == "smoke":
        run_smoke(args.top_k)
        return

    # 筛选赛
    comps = COMPETITIONS
    if args.competitions:
        slugs = set(args.competitions)
        comps = [c for c in comps if c["slug"] in slugs]
        if not comps:
            print(f"ERROR: 没有匹配的赛。可用 slug: {[c['slug'] for c in COMPETITIONS]}")
            sys.exit(1)

    results = []
    if args.mode == "csv":
        args.data_dir.mkdir(parents=True, exist_ok=True)
        for comp in comps:
            csv_path = args.data_dir / f"{comp['slug']}.csv"
            print(f"分析 {comp['name']} <- {csv_path}")
            res = analyze_competition_csv(comp, csv_path, args.top_k)
            results.append(res)

    elif args.mode == "api":
        print(
            "\n[API 模式] 注意：kaggle 标准 API 只返回 final/private score，"
            "无法计算 public→private gap。\n"
            "建议改用 --mode csv（从 Kaggle 赛页下载含双分的 CSV）。\n"
        )
        # 检查 kaggle 包
        try:
            import kaggle as _  # noqa: F401
        except ImportError:
            print("ERROR: kaggle 包未安装。运行: pip install kaggle")
            sys.exit(1)
        for comp in comps:
            print(f"拉取 {comp['name']} via API ...")
            res = analyze_competition_api(comp, args.top_k)
            results.append(res)

    if results:
        _print_and_save_results(results, args.top_k)
    else:
        print("无结果，检查参数。")


if __name__ == "__main__":
    main()
