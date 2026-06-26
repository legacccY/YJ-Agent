"""
build_fc_cc200_from_braingb.py
================================
BrainGB abide.npy (CC200 Pearson FC) → HyperGALE fc_large_data_cc200.npy

【偏离论文声明（红线合规注释）】
  HyperGALE 论文原用 ABIDE-II / Schaefer400 (400节点) / LedoitWolf full-correlation FC。
  本脚本改用 ABIDE-I / CC200 (200节点) / Pearson FC，原因：
    1. HPC 下载 ABIDE-I func_preproc 实测 0.08MB/s → 43GB 需 6天，不可行。
    2. BrainGB 泳道已产出 abide.npy (CC200 Pearson FC)，零下载成本。
    3. 与 BrainGB 完全同 cohort + atlas + split，Gate2 纯比 GNN vs 超图架构，
       无数据差异干扰（Schaefer400 路线则 BrainGB/HyperGALE 用不同 cohort）。
  FC 方法从 LedoitWolf correlation 降为 Pearson（随 BrainGB 已有数据）。
  节点数从 400 降为 200。k-NN 超边 k=40 沿用论文值（见 TODO 注释）。

【数据源】
  vendor/BrainGB/examples/datasets/ABIDE/abide.npy
  → dict:
      "corr":     (871, 200, 200) float64 — CC200 Pearson FC（BrainGB Adj() 会归一化）
      "label":    (871,) int — 1=ASD, 0=TD
      "sub_ids":  (871,) — SUB_ID（与 data/external/abide1/split_indices.csv 对齐）
      "site_ids": (871,) — SITE_ID 字符串

【HyperGALE 期望的 fc_large_data.npy 格式（source/dataset/fc.py）】
  fc_data = np.load(path, allow_pickle=True).item()
  → fc_data["corr"]  : (N, 200, 200) float32  ← float64→float32
  → fc_data["label"] : (N,) float32            ← int 1=ASD/0=TD → float32（方向一致）
  → fc_data["site"]  : (N,) str/object         ← site_ids

【label 编码验证】
  abide.npy label: 1=ASD, 0=TD  ← (DX_GROUP==1).astype(int) 见 build_graphs.py
  HyperGALE BCEWithLogitsLoss target: float, 1=ASD, 0=TD ← 方向一致，直接 astype float32

【node_sz 自动推断】
  fc.py L35: cfg.dataset.node_sz, cfg.dataset.node_feature_sz = final_pearson.shape[1:]
  → 只要 corr shape 是 (N,200,200)，vendor 自动拿到 200，无需硬改 config。

【k-NN 超边 k 值】
  # TODO: k=40 是论文 Schaefer400(400节点) 的值，沿用到 CC200(200节点)。
  # 200节点用 k=40 意味每条超边覆盖 41/200=20.5% 节点（原 41/400=10.25%）。
  # 覆盖率加倍可能影响超图连通性，但数值上合法（k < n_nodes）。
  # 论文无 cc200 下 k 消融，此处保留 k=40 待 Gate2 调参验证，不臆改。

运行（HPC 或本地，秒级，无网络需求）：
  python src/hypergale_lane/build_fc_cc200_from_braingb.py \\
      --abide-npy   vendor/BrainGB/examples/datasets/ABIDE/abide.npy \\
      --output      data/external/abide1_cc200/fc_large_data_cc200.npy \\
      --meta-output data/external/abide1_cc200/abide1_cc200_meta.csv
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ABIDE_NPY   = _ROOT / "vendor" / "BrainGB" / "examples" / "datasets" / "ABIDE" / "abide.npy"
DEFAULT_OUTPUT      = _ROOT / "data" / "external" / "abide1_cc200" / "fc_large_data_cc200.npy"
DEFAULT_META_OUTPUT = _ROOT / "data" / "external" / "abide1_cc200" / "abide1_cc200_meta.csv"


def convert(abide_npy: Path, output: Path, meta_output: Path) -> None:
    """
    abide.npy → fc_large_data_cc200.npy + meta CSV。

    流程：
      1. 读 abide.npy（BrainGB 格式）
      2. 校验 corr/label/site 字段完整性 + label 编码方向
      3. 转 float32 / 提取 site 字符串
      4. 保存 HyperGALE 格式 .npy
      5. 保存 meta CSV（sub_id/site_id/label/fc_idx）供 make_split_cc200.py 用
    """
    if not abide_npy.exists():
        logger.error(
            "abide.npy 不存在: %s\n"
            "请先运行 src/braingb_lane/build_graphs.py 产出该文件。",
            abide_npy,
        )
        sys.exit(1)

    # ── Step 1: 读 BrainGB abide.npy
    logger.info("读取 abide.npy: %s", abide_npy)
    data = np.load(str(abide_npy), allow_pickle=True).item()

    corr     = data.get("corr")      # (N, 200, 200)
    labels   = data.get("label")     # (N,) int
    sub_ids  = data.get("sub_ids")   # (N,)
    site_ids = data.get("site_ids")  # (N,)

    # ── Step 2: 校验
    if corr is None or labels is None:
        logger.error("abide.npy 缺少 'corr' 或 'label' 键，实际键: %s", list(data.keys()))
        sys.exit(1)

    N = corr.shape[0]
    assert corr.ndim == 3, f"corr 应为 3D，实际 {corr.ndim}D shape={corr.shape}"
    assert corr.shape[1] == corr.shape[2], (
        f"corr 非方阵: shape={corr.shape}"
    )
    assert len(labels) == N, f"label 长度 {len(labels)} != corr N={N}"

    n_rois = corr.shape[1]
    logger.info(
        "abide.npy: N=%d, n_rois=%d, corr dtype=%s, label dtype=%s",
        N, n_rois, corr.dtype, labels.dtype,
    )

    # ── label 编码方向验证（红线）
    # abide.npy: (DX_GROUP==1).astype(int) → 1=ASD, 0=TD（见 build_graphs.py L184）
    # HyperGALE BCEWithLogitsLoss target: float, 1=ASD, 0=TD → 方向一致
    unique_labels = set(labels.tolist())
    if not unique_labels.issubset({0, 1, 0.0, 1.0}):
        logger.error("label 值域异常: %s（预期 {0,1}）", unique_labels)
        sys.exit(1)

    n_asd = int((labels == 1).sum())
    n_td  = int((labels == 0).sum())
    logger.info(
        "label 分布验证: ASD(label=1)=%d (%.1f%%), TD(label=0)=%d (%.1f%%) — 编码方向 OK",
        n_asd, 100 * n_asd / N, n_td, 100 * n_td / N,
    )
    assert n_asd > 0 and n_td > 0, "label 只有单类，数据有误"

    # ── site 处理
    if site_ids is None:
        logger.warning("abide.npy 无 'site_ids' 键，用占位 'UNKNOWN'")
        site_arr = np.array(["UNKNOWN"] * N)
    else:
        # 确保是字符串数组（有时是数值 site index）
        site_arr = np.array([str(s) for s in site_ids])

    n_sites = len(set(site_arr))
    logger.info("site 数: %d，样例: %s", n_sites, sorted(set(site_arr))[:5])

    # ── sub_ids 处理
    if sub_ids is None:
        logger.warning("abide.npy 无 'sub_ids' 键，用行索引作为 sub_id")
        sub_id_arr = np.array([str(i) for i in range(N)])
    else:
        # 统一用 str(int(...)) 去前导零，与 split_indices.csv SUB_ID 对齐
        sub_id_arr = np.array([str(int(s)) if str(s).isdigit() else str(s) for s in sub_ids])

    # ── Step 3: 转 float32
    corr_f32  = corr.astype(np.float32)     # (N, 200, 200) float32
    label_f32 = labels.astype(np.float32)   # (N,) float32，1.0=ASD, 0.0=TD

    # ── Step 4: 保存 fc_large_data_cc200.npy（HyperGALE 格式）
    output.parent.mkdir(parents=True, exist_ok=True)
    fc_data = {
        "corr":  corr_f32,   # (N, 200, 200) float32
        "label": label_f32,  # (N,) float32, 1.0=ASD, 0.0=TD
        "site":  site_arr,   # (N,) str
    }
    np.save(str(output), fc_data)
    logger.info("fc_large_data_cc200.npy 已保存 → %s", output)
    logger.info("文件大小: %.1f MB", output.stat().st_size / 1e6)
    logger.info(
        "内容: corr%s float32, label%s float32, site%s str",
        corr_f32.shape, label_f32.shape, site_arr.shape,
    )

    # ── Step 5: 保存 meta CSV（供 make_split_cc200.py + 调试）
    meta_df = pd.DataFrame({
        "sub_id":  sub_id_arr,
        "site_id": site_arr,
        "label":   label_f32.astype(int).tolist(),   # int 列更易读
        "dx_group": [1 if l == 1.0 else 2 for l in label_f32],
        "fc_idx":  list(range(N)),   # fc_large_data_cc200.npy 中的行索引
    })
    meta_output.parent.mkdir(parents=True, exist_ok=True)
    meta_df.to_csv(meta_output, index=False)
    logger.info("meta CSV 已保存 → %s", meta_output)

    # ── 最终汇总
    logger.info(
        "完成: N=%d, n_rois=%d(CC200), ASD=%d, TD=%d, sites=%d",
        N, n_rois, n_asd, n_td, n_sites,
    )
    logger.info("后续步骤:")
    logger.info("  1. python src/hypergale_lane/make_split_cc200.py --meta %s", meta_output)
    logger.info("  2. python src/hypergale_lane/train_hypergale.py --fc-path %s", output)


def parse_args():
    p = argparse.ArgumentParser(
        description="BrainGB abide.npy (CC200) → HyperGALE fc_large_data_cc200.npy"
    )
    p.add_argument(
        "--abide-npy", type=Path, default=DEFAULT_ABIDE_NPY,
        help="BrainGB 产出的 abide.npy（含 corr/label/sub_ids/site_ids）",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="输出 fc_large_data_cc200.npy 路径（HyperGALE --fc-path 参数）",
    )
    p.add_argument(
        "--meta-output", type=Path, default=DEFAULT_META_OUTPUT,
        help="输出 meta CSV 路径（供 make_split_cc200.py 读取）",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    convert(
        abide_npy=args.abide_npy,
        output=args.output,
        meta_output=args.meta_output,
    )
