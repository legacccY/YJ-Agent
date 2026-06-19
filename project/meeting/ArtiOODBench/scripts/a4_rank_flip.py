"""
a4_rank_flip.py
服务: ArtiOODBench Gate1 R8（纯分析，判据 A-4 第二口径）
lever: L3 重排命门

【做什么】
读 R4(raw) / R5(cleanC) + R6(cleanA)/R7(cleanB) ranking CSV，
输出：
  1. a4_rank_flip.csv：
     - 口径1 bootstrap CI Spearman(原,C)（判 CI 上界<0.7 或 top1 掉出 top3）
       注：CI 值由 l3_ood_rerank.py 已算，此处读取并重报
     - 口径2 机制可解释表（实测掉幅顺序 vs 预登记假设 MDS>KNN/ViM>MSP）
  2. 机制可解释性判定：
     A-4 判据要求掉幅顺序符合 MDS>KNN/ViM>MSP 敏感度假设
     （Mahalanobis 最依赖距离=最受 artifact 影响，MSP 最粗糙=最不依赖）

【运行】
  # smoke（合成 ranking）
  python a4_rank_flip.py --smoke

  # 真实数据（l3_ood_rerank.py 跑完后）
  python a4_rank_flip.py
"""

import argparse
import csv
import io
import sys
from pathlib import Path

import numpy as np

# Windows GBK 终端安全
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 路径常量
# ============================================================
OUT_DIR = Path(__file__).resolve().parent.parent / "results"
OUT_L3_RAW = OUT_DIR / "l3_raw_ranking.csv"
OUT_L3_CLEAN_C = OUT_DIR / "l3_cleanC_ranking.csv"
OUT_BOOTSTRAP = OUT_DIR / "a4_bootstrap_spearman.csv"
OUT_L3_CLEAN_A = OUT_DIR / "l3_cleanA_ranking.csv"  # 可选
OUT_L3_CLEAN_B = OUT_DIR / "l3_cleanB_ranking.csv"  # 可选

OUT_A4 = OUT_DIR / "a4_rank_flip.csv"

OOD_METHODS = ["MSP", "ODIN", "Energy", "MDS", "KNN", "ViM", "GradNorm"]

# 预登记机制假设（A-4 口径2，冻结）：
# 去污染后 AUROC 掉幅：MDS 最大 > KNN/ViM 居中 > MSP 最小
# 理由：MDS 对特征空间几何最敏感（Mahalanobis 依赖协方差），
#       KNN/ViM 次之（邻域/子空间），MSP 最粗糙（仅看 max prob）
MECHANISM_HYPOTHESIS = {
    "sensitivity_order": ["MDS", "KNN", "ViM", "MSP"],  # 高到低敏感度（掉幅大到小）
    "description": "去污染后 AUROC 掉幅顺序假设: MDS > KNN/ViM > MSP（预登记）",
}


# ============================================================
# 纯 numpy Spearman（避 scipy）
# ============================================================
def spearman_numpy(x: np.ndarray, y: np.ndarray) -> float:
    def rankdata(arr):
        n = len(arr)
        idx = np.argsort(arr)
        ranks = np.empty(n, dtype=np.float64)
        ranks[idx] = np.arange(1, n + 1, dtype=np.float64)
        sorted_arr = arr[idx]
        i = 0
        while i < n:
            j = i
            while j < n and sorted_arr[j] == sorted_arr[i]:
                j += 1
            ranks[idx[i:j]] = (i + 1 + j) / 2.0
            i = j
        return ranks
    rx, ry = rankdata(x.astype(np.float64)), rankdata(y.astype(np.float64))
    rx_c, ry_c = rx - rx.mean(), ry - ry.mean()
    denom = np.sqrt((rx_c**2).sum()) * np.sqrt((ry_c**2).sum())
    return float((rx_c * ry_c).sum() / denom) if denom > 1e-12 else 0.0


# ============================================================
# 读 ranking CSV
# ============================================================
def load_ranking_csv(path: Path) -> dict:
    """返回 {pair -> {method -> {rank, auroc}}}。"""
    if not path.exists():
        return {}
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pair = row.get("pair", "unknown")
            method = row["method"]
            result.setdefault(pair, {})[method] = {
                "rank": int(row["rank"]),
                "auroc": float(row["auroc"]) if row["auroc"] not in ("nan", "") else float("nan"),
            }
    return result


def load_bootstrap_csv(path: Path) -> dict:
    """返回 {pair -> {spearman_point, ci_lower, ci_upper, ...}}。"""
    if not path.exists():
        return {}
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pair = row.get("pair", "unknown")
            result[pair] = {k: row[k] for k in row}
    return result


# ============================================================
# 机制可解释性检验
# ============================================================
def check_mechanism(
    raw_aurocs: dict, clean_aurocs: dict, pair_name: str
) -> dict:
    """
    口径2：检验实测 AUROC 掉幅顺序是否符合预登记假设。
    返回 {method -> delta, rank_in_drop, hypothesis_rank, match}。
    """
    hypothesis = MECHANISM_HYPOTHESIS["sensitivity_order"]
    # 计算掉幅（raw - clean，越大=受 artifact 影响越大）
    drops = {}
    for method in OOD_METHODS:
        raw = raw_aurocs.get(method, {}).get("auroc", float("nan"))
        clean = clean_aurocs.get(method, {}).get("auroc", float("nan"))
        if not (np.isnan(raw) or np.isnan(clean)):
            drops[method] = raw - clean
        else:
            drops[method] = float("nan")

    # 按掉幅降序排列
    valid_drops = [(m, d) for m, d in drops.items() if not np.isnan(d)]
    valid_drops.sort(key=lambda x: -x[1])
    actual_order = [m for m, _ in valid_drops]

    rows = []
    for i, (method, delta) in enumerate(valid_drops):
        actual_rank = i + 1
        # 在预登记假设中的排名（只检验 hypothesis 列出的方法）
        hyp_rank = hypothesis.index(method) + 1 if method in hypothesis else None
        rows.append({
            "pair": pair_name,
            "method": method,
            "raw_auroc": round(raw_aurocs.get(method, {}).get("auroc", float("nan")), 4),
            "clean_auroc": round(clean_aurocs.get(method, {}).get("auroc", float("nan")), 4),
            "delta_drop": round(delta, 4),
            "actual_rank_by_drop": actual_rank,
            "hypothesis_rank": hyp_rank if hyp_rank else "N/A",
        })

    # Spearman 比较 actual_order vs hypothesis（仅对共有方法）
    common = [m for m in actual_order if m in hypothesis]
    if len(common) >= 2:
        actual_ranks_common = [actual_order.index(m) + 1 for m in common]
        hyp_ranks_common = [hypothesis.index(m) + 1 for m in common]
        mech_spearman = spearman_numpy(np.array(actual_ranks_common),
                                        np.array(hyp_ranks_common))
        mech_match = mech_spearman >= 0.5  # 大于 0.5 视为方向一致
    else:
        mech_spearman = float("nan")
        mech_match = False

    return rows, mech_spearman, mech_match, actual_order


# ============================================================
# 主逻辑
# ============================================================
def main(smoke: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if smoke:
        # 合成 ranking（模拟 l3 输出已就位）
        print("[A4] SMOKE: 合成 ranking 数据")
        rng = np.random.RandomState(42)
        raw_aurocs_mock = {
            "NIH_vs_VinDr": {
                m: {"rank": i + 1,
                    "auroc": round(float(0.75 - 0.05 * i + rng.randn() * 0.02), 4)}
                for i, m in enumerate(OOD_METHODS)
            }
        }
        clean_c_aurocs_mock = {
            "NIH_vs_VinDr": {
                m: {"rank": i + 1,
                    "auroc": round(float(0.65 - 0.04 * i + rng.randn() * 0.03), 4)}
                for i, m in enumerate(["MDS", "ViM", "KNN", "GradNorm",
                                        "Energy", "ODIN", "MSP"])
            }
        }
        boot_mock = {
            "NIH_vs_VinDr": {
                "spearman_point": "0.4286",
                "ci_lower": "0.1",
                "ci_upper": "0.65",
                "ci_upper_lt_0.7": "1",
                "top1_orig": "MSP",
                "top1_cleanC_rank": "5",
                "top1_dropped_from_top3": "1",
                "A4_verdict": "A-4 PASS (排名实质改变)",
            }
        }
        _run_analysis(raw_aurocs_mock, clean_c_aurocs_mock, boot_mock,
                      load_ranking_csv(OUT_L3_CLEAN_A), load_ranking_csv(OUT_L3_CLEAN_B))
        return

    # 真实数据
    raw_ranking = load_ranking_csv(OUT_L3_RAW)
    clean_c_ranking = load_ranking_csv(OUT_L3_CLEAN_C)
    bootstrap_data = load_bootstrap_csv(OUT_BOOTSTRAP)
    clean_a_ranking = load_ranking_csv(OUT_L3_CLEAN_A)
    clean_b_ranking = load_ranking_csv(OUT_L3_CLEAN_B)

    if not raw_ranking:
        print(
            f"[ERROR] l3_raw_ranking.csv 未找到: {OUT_L3_RAW}\n"
            "请先运行 l3_ood_rerank.py",
            file=sys.stderr,
        )
        sys.exit(1)

    _run_analysis(raw_ranking, clean_c_ranking, bootstrap_data,
                  clean_a_ranking, clean_b_ranking)


def _run_analysis(raw_ranking, clean_c_ranking, bootstrap_data,
                  clean_a_ranking, clean_b_ranking):
    """对所有 pair 执行 A-4 两口径分析。"""
    all_rows = []

    for pair_name in raw_ranking:
        raw_aurocs = raw_ranking[pair_name]
        clean_aurocs = clean_c_ranking.get(pair_name, {})
        boot = bootstrap_data.get(pair_name, {})

        print(f"\n[A4] pair={pair_name}")

        # 口径1: bootstrap CI Spearman（从 l3 输出读取）
        spearman_pt = boot.get("spearman_point", "nan")
        ci_lower = boot.get("ci_lower", "nan")
        ci_upper = boot.get("ci_upper", "nan")
        ci_upper_lt_07 = boot.get("ci_upper_lt_0.7", "?")
        top1_orig = boot.get("top1_orig", "?")
        top1_rank_c = boot.get("top1_cleanC_rank", "?")
        top1_dropped = boot.get("top1_dropped_from_top3", "?")
        # 注意：不直接透传 bootstrap CSV 的 A4_verdict 旧字段（可能来自陈旧 run）
        # a4_verdict 在下方 AND 门中本地重算，见下文

        print(f"  [口径1] Spearman(原,C)={spearman_pt} "
              f"CI=[{ci_lower},{ci_upper}]")
        print(f"  [口径1] CI上界<0.7: {ci_upper_lt_07}, "
              f"top1({top1_orig})掉出top3: {top1_dropped}")
        # 口径1 单独 ci1 判决（最终 AND 门 verdict 在口径2 分析后本地重算）

        # 口径2: 机制可解释性
        if clean_aurocs:
            mech_rows, mech_spearman, mech_match, actual_order = \
                check_mechanism(raw_aurocs, clean_aurocs, pair_name)

            print(f"  [口径2] 机制假设: {MECHANISM_HYPOTHESIS['description']}")
            print(f"  [口径2] 实测掉幅顺序: {actual_order[:5]}")
            print(f"  [口径2] 机制 Spearman(实测,假设)={mech_spearman:.4f}, "
                  f"方向匹配(≥0.5): {mech_match}")

            # A-4 AND 门本地重算（冻结判据，不透传 bootstrap CSV 旧字段）：
            # PASS iff (ci1_upper_lt_0.7==1 OR ci1_top1_dropped==1) AND (ci2_mech_match==1)
            # 参见 02_ACCEPTANCE.md A-4 预登记口径
            try:
                ci1_pass = (int(ci_upper_lt_07) == 1) or (int(top1_dropped) == 1)
            except (ValueError, TypeError):
                ci1_pass = False
            ci2_pass = bool(mech_match)  # mech_match already bool from check_mechanism
            if ci1_pass and ci2_pass:
                a4_verdict_local = "A-4 PASS (排名实质改变)"
            else:
                a4_verdict_local = "A-4 FAIL"

            for mr in mech_rows:
                mr.update({
                    "subset": "cleanC",
                    "ci1_spearman": spearman_pt,
                    "ci1_ci_lower": ci_lower,
                    "ci1_ci_upper": ci_upper,
                    "ci1_upper_lt_0.7": ci_upper_lt_07,
                    "ci1_top1_dropped": top1_dropped,
                    "ci2_mech_spearman": round(mech_spearman, 4) if not np.isnan(mech_spearman) else "nan",
                    "ci2_mech_match_gte_0.5": int(mech_match),
                    "a4_verdict": a4_verdict_local,
                })
                all_rows.append(mr)
        else:
            print(f"  [口径2] cleanC ranking 未就位，跳过机制分析")
            # cleanC 缺失时 ci2 腿无法评估 → AND 门必然 FAIL
            a4_verdict_local = "A-4 FAIL (ci2 缺失)"
            # 仍写口径1
            all_rows.append({
                "pair": pair_name,
                "method": "N/A",
                "subset": "cleanC",
                "raw_auroc": "nan",
                "clean_auroc": "nan",
                "delta_drop": "nan",
                "actual_rank_by_drop": "nan",
                "hypothesis_rank": "nan",
                "ci1_spearman": spearman_pt,
                "ci1_ci_lower": ci_lower,
                "ci1_ci_upper": ci_upper,
                "ci1_upper_lt_0.7": ci_upper_lt_07,
                "ci1_top1_dropped": top1_dropped,
                "ci2_mech_spearman": "nan",
                "ci2_mech_match_gte_0.5": "nan",
                "a4_verdict": a4_verdict_local,
            })

        # 方案 A / B 附录摘要
        for scheme, ranking_dict in [("cleanA", clean_a_ranking),
                                      ("cleanB", clean_b_ranking)]:
            if pair_name in ranking_dict:
                aurocs_s = ranking_dict[pair_name]
                raw_vals = [raw_aurocs.get(m, {}).get("auroc", float("nan"))
                            for m in OOD_METHODS]
                clean_vals = [aurocs_s.get(m, {}).get("auroc", float("nan"))
                              for m in OOD_METHODS]
                orig_ranks = [raw_aurocs.get(m, {}).get("rank", 99) for m in OOD_METHODS]
                clean_ranks_s = [aurocs_s.get(m, {}).get("rank", 99) for m in OOD_METHODS]
                sp_s = spearman_numpy(np.array(orig_ranks, dtype=np.float64),
                                       np.array(clean_ranks_s, dtype=np.float64))
                print(f"  [{scheme}] Spearman(原,{scheme})={sp_s:.4f} (附录 robustness)")

    if not all_rows:
        print("[A4] 无数据可输出", file=sys.stderr)
        # 写空 CSV
        all_rows = []

    fieldnames = [
        "pair", "method", "subset",
        "raw_auroc", "clean_auroc", "delta_drop",
        "actual_rank_by_drop", "hypothesis_rank",
        "ci1_spearman", "ci1_ci_lower", "ci1_ci_upper",
        "ci1_upper_lt_0.7", "ci1_top1_dropped",
        "ci2_mech_spearman", "ci2_mech_match_gte_0.5",
        "a4_verdict",
    ]
    with open(OUT_A4, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n[A4] -> {OUT_A4}")

    # 最终判决摘要
    print("\n" + "=" * 60)
    print("A-4 命门判决摘要")
    print("-" * 60)
    seen_pairs = set()
    for r in all_rows:
        pair = r["pair"]
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        verdict = r.get("a4_verdict", "?")
        ci_flag = r.get("ci1_upper_lt_0.7", "?")
        mech_flag = r.get("ci2_mech_match_gte_0.5", "?")
        print(f"  {pair}: {verdict}")
        print(f"    口径1 CI上界<0.7={ci_flag}, 口径2 mech_match={mech_flag}")
    print("=" * 60)
    print("\n注意 (PR-F2): A-4 命门只用方案C。方案A/B仅附录 robustness，")
    print("禁止因方案A/B不显著而否定命门结论（杜绝隐性 p-hacking）。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A-4 rank flip analysis (R8)")
    parser.add_argument("--smoke", action="store_true",
                        help="合成 ranking smoke 测试")
    args = parser.parse_args()
    main(smoke=args.smoke)
