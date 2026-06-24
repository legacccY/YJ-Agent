"""
subband_zero.py — WaveFidBench Gate1 L1 初验：子带置零消融
服务项目：WaveFidBench (wavefid) Gate1，lever L1 频带承载差异初验

功能：
  加载冻结分类器权重，对测试集执行 5 种子带置零条件：
    W-base: 不置零，验往返重建 acc ≈ 原图 acc（生效锚点）
    W-LL:   置零低频近似（Yl=0）
    W-LH:   置零水平高频（Yh[0][:,:,0,:,:]=0）  # idx 0=LH，researcher T4 核实
    W-HL:   置零垂直高频（Yh[0][:,:,1,:,:]=0）  # idx 1=HL
    W-HH:   置零对角高频（Yh[0][:,:,2,:,:]=0）  # idx 2=HH

⚠️ Gate1 只出数字 + 相对 acc 损失；不下 L1 显著性结论（留 Gate2 防 HARKing）

wavelet 超参（researcher T4 核实）：
  J=1, wave='db1', mode='symmetric'（symmetric 减边界 artifact，T4 建议）
  Yh[0] idx: 0=LH / 1=HL / 2=HH（finest-first，注意与 PyWavelets 方向相反）
  DWT→IDWT 同 wave+mode，fp32 重建误差 ~1e-6

用法：
  python src/subband_zero.py \\
      --config configs/gate1_kaggle.yaml \\
      --data_root /path/to/data \\
      --split_csv_dir log/splits \\
      --checkpoint log/checkpoints/resnet50_seed42_best.pt
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

# pytorch_wavelets（官方：https://github.com/fbcotter/pytorch_wavelets）
from pytorch_wavelets import DWTForward, DWTInverse

from train_classifier import build_backbone, MRIDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# =========================================================
# 子带置零条件定义
# =========================================================

def make_conditions():
    """
    返回 list of (name, zero_fn)
    zero_fn(Yl, Yh) -> (Yl', Yh') 均为 clone 后修改，不破坏原 tensor
    Yh[0]: shape (N, C, 3, H', W')  其中 dim=2: 0=LH, 1=HL, 2=HH（researcher T4 核实）
    """
    def w_base(Yl, Yh):
        # 不置零，用于验往返重建 acc ≈ 原图 acc
        return Yl.clone(), [yh.clone() for yh in Yh]

    def w_ll(Yl, Yh):
        Yl2 = torch.zeros_like(Yl)
        Yh2 = [yh.clone() for yh in Yh]
        return Yl2, Yh2

    def w_lh(Yl, Yh):
        # idx 0 = LH（水平细节，researcher T4 核实）
        Yh2 = [yh.clone() for yh in Yh]
        Yh2[0][:, :, 0, :, :] = 0.0
        return Yl.clone(), Yh2

    def w_hl(Yl, Yh):
        # idx 1 = HL（垂直细节）
        Yh2 = [yh.clone() for yh in Yh]
        Yh2[0][:, :, 1, :, :] = 0.0
        return Yl.clone(), Yh2

    def w_hh(Yl, Yh):
        # idx 2 = HH（对角细节）
        Yh2 = [yh.clone() for yh in Yh]
        Yh2[0][:, :, 2, :, :] = 0.0
        return Yl.clone(), Yh2

    return [
        ("W-base", w_base),
        ("W-LL",   w_ll),
        ("W-LH",   w_lh),
        ("W-HL",   w_hl),
        ("W-HH",   w_hh),
    ]


# =========================================================
# 基线直通 acc（无 DWT）
# =========================================================

def eval_direct(model, loader, device) -> float:
    model.eval()
    correct, total = 0, 0
    with torch.no_grad():
        for imgs, labels in loader:
            imgs, labels = imgs.to(device), labels.to(device)
            preds = model(imgs).argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)
    return correct / total if total > 0 else 0.0


# =========================================================
# 子带消融评估（DWT→置零→IDWT→分类器）
# =========================================================

def eval_subband_zero(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    dwt: DWTForward,
    idwt: DWTInverse,
    zero_fn,
) -> float:
    """对整个 loader 做子带置零后的推理，返回 acc。"""
    model.eval()
    dwt.eval()
    correct, total = 0, 0

    with torch.no_grad():
        for imgs, labels in loader:
            imgs, labels = imgs.to(device), labels.to(device)

            # DWT
            Yl, Yh = dwt(imgs)  # Yl: (N,C,H',W')  Yh[0]: (N,C,3,H',W')

            # 子带置零
            Yl_mod, Yh_mod = zero_fn(Yl, Yh)

            # IDWT 重建回图像域
            imgs_rec = idwt((Yl_mod, Yh_mod))

            # 裁回原始尺寸（IDWT 可能因 padding 产生 off-by-one）
            imgs_rec = imgs_rec[:, :, : imgs.shape[2], : imgs.shape[3]]

            # 喂分类器
            preds = model(imgs_rec).argmax(dim=1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)

    return correct / total if total > 0 else 0.0


# =========================================================
# 主入口
# =========================================================

def main():
    parser = argparse.ArgumentParser(description="WaveFidBench subband_zero.py")
    parser.add_argument("--config", required=True, help="YAML config 路径")
    parser.add_argument("--data_root", required=True, help="数据根目录")
    parser.add_argument(
        "--split_csv_dir", default=None, help="split csv 目录（默认从 config 推导）"
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="train_classifier.py 输出的 .pt 权重路径",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    cfg = load_config(args.config)

    project_root = Path(__file__).parent.parent
    log_dir = project_root / cfg.get("log_dir", "log")
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.split_csv_dir is None:
        args.split_csv_dir = str(project_root / cfg.get("split_csv_dir", "log/splits"))
    split_csv_dir = Path(args.split_csv_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"设备: {device}")

    # 加载模型（冻结推理，不训练）
    backbone_name = cfg.get("backbone", "resnet50")
    num_classes = cfg.get("num_classes", 4)
    model = build_backbone(backbone_name, num_classes, pretrained=False)
    ckpt = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(ckpt)
    model = model.to(device)
    model.eval()
    logger.info(f"权重已加载：{args.checkpoint}")

    # DataLoader
    mean = cfg["normalize_mean"]
    std = cfg["normalize_std"]
    img_size = cfg["image_size"]
    eval_transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])
    test_ds = MRIDataset(split_csv_dir / "test.csv", transform=eval_transform)
    test_loader = DataLoader(
        test_ds,
        batch_size=cfg.get("batch_size", 32),
        shuffle=False,
        num_workers=cfg.get("num_workers", 0),
        pin_memory=cfg.get("pin_memory", False),
        multiprocessing_context="spawn" if cfg.get("num_workers", 0) > 0 else None,
    )
    logger.info(f"test set: {len(test_ds)} 张")

    # DWT / IDWT（researcher T4：mode='symmetric' 减边界 artifact）
    dwt = DWTForward(J=1, wave="db1", mode="symmetric").to(device)
    idwt = DWTInverse(wave="db1", mode="symmetric").to(device)

    # 基线直通 acc
    base_direct_acc = eval_direct(model, test_loader, device)
    logger.info(f"直通 acc（无 DWT）= {base_direct_acc:.4f}")

    # 5 种置零条件
    conditions = make_conditions()
    results = []

    for cond_name, zero_fn in conditions:
        acc = eval_subband_zero(model, test_loader, device, dwt, idwt, zero_fn)
        acc_drop = base_direct_acc - acc
        logger.info(f"  {cond_name}: acc={acc:.4f}  acc_drop={acc_drop:+.4f}")
        results.append({
            "condition": cond_name,
            "test_acc": acc,
            "acc_drop_vs_direct": acc_drop,
        })

    # 写 csv
    df_res = pd.DataFrame(results)
    df_res["backbone"] = backbone_name
    df_res["seed"] = args.seed
    df_res["split_mode"] = cfg.get("split_mode", "unknown")
    df_res["base_direct_acc"] = base_direct_acc
    df_res["timestamp"] = datetime.now().isoformat()

    results_csv = log_dir / "subband_zero_results.csv"
    df_res.to_csv(results_csv, index=False)
    logger.info(f"结果 csv 已写 -> {results_csv}")

    # state.json
    state = {
        "script": "subband_zero.py",
        "timestamp": datetime.now().isoformat(),
        "backbone": backbone_name,
        "checkpoint": args.checkpoint,
        "seed": args.seed,
        "split_mode": cfg.get("split_mode", "unknown"),
        "wavelet_params": {"J": 1, "wave": "db1", "mode": "symmetric"},
        "subband_idx_note": "Yh[0] dim=2: 0=LH / 1=HL / 2=HH（pytorch_wavelets finest-first，researcher T4 核实）",
        "base_direct_acc": base_direct_acc,
        "results": results,
        "gate1_note": "Gate1 只出数字，不下 L1 显著性结论（留 Gate2 防 HARKing）",
    }
    state_path = log_dir / "subband_zero_state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info(f"state.json 已写 -> {state_path}")

    print(f"\nDone. results -> {results_csv}")
    print(df_res[["condition", "test_acc", "acc_drop_vs_direct"]].to_string(index=False))


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    main()
