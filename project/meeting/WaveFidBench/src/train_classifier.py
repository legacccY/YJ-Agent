"""
train_classifier.py — WaveFidBench Gate1 分类器训练脚本
服务项目：WaveFidBench (wavefid) Gate1，lever L1 地基

功能：
- backbone: resnet50 / vit_b_16（torchvision，ImageNet 预训练）
- 灰度 MRI repeat 成 3 通道，224×224
- 类不均衡：CrossEntropyLoss class_weight（倒频率）
- 增强：horizontal flip + rotation±15°（禁 vertical flip）
- Windows spawn 规范（if __name__=='__main__' 守卫，pin_memory=false）
- 输出：checkpoint + test acc + macro-F1 + 混淆矩阵 + csv + state.json

用法：
  python src/train_classifier.py \\
      --config configs/gate1_kaggle.yaml \\
      --data_root /path/to/data \\
      --split_csv_dir log/splits \\
      --seed 42
"""

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yaml
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# =========================================================
# Dataset
# =========================================================

class MRIDataset(Dataset):
    """加载 data_split.py 生成的 split csv 中的图像。"""

    def __init__(self, csv_path: Path, transform=None):
        self.df = pd.read_csv(csv_path)
        self.transform = transform
        # 构建 label -> idx 映射（排序保证稳定）
        self.classes = sorted(self.df["label"].unique())
        self.class_to_idx = {c: i for i, c in enumerate(self.classes)}
        self.idx_to_class = {i: c for c, i in self.class_to_idx.items()}

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = Image.open(row["filepath"]).convert("RGB")  # 灰度 repeat 3ch via RGB
        if self.transform:
            img = self.transform(img)
        label = self.class_to_idx[row["label"]]
        return img, label


# =========================================================
# 构建 backbone
# =========================================================

def build_backbone(backbone_name: str, num_classes: int, pretrained: bool) -> nn.Module:
    if backbone_name == "resnet50":
        weights = models.ResNet50_Weights.IMAGENET1K_V1 if pretrained else None
        model = models.resnet50(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif backbone_name == "vit_b_16":
        weights = models.ViT_B_16_Weights.IMAGENET1K_V1 if pretrained else None
        model = models.vit_b_16(weights=weights)
        # torchvision ViT-B/16 head = model.heads.head
        in_features = model.heads.head.in_features
        model.heads.head = nn.Linear(in_features, num_classes)
    else:
        raise ValueError(f"未知 backbone: {backbone_name}（支持 resnet50 / vit_b_16）")
    return model


# =========================================================
# 计算 class weight
# =========================================================

def compute_class_weights(train_csv: Path, class_to_idx: dict, device: torch.device) -> torch.Tensor:
    df = pd.read_csv(train_csv)
    counts = df["label"].value_counts()
    n_classes = len(class_to_idx)
    weights = torch.zeros(n_classes, dtype=torch.float32)
    for cls, idx in class_to_idx.items():
        cnt = counts.get(cls, 1)
        weights[idx] = 1.0 / cnt
    # 归一化（可选，保持量级稳定）
    weights = weights / weights.sum() * n_classes
    logger.info(f"class_weights = {weights.tolist()}")
    return weights.to(device)


# =========================================================
# 评估
# =========================================================

def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> dict:
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in loader:
            imgs, labels = imgs.to(device), labels.to(device)
            outputs = model(imgs)
            preds = outputs.argmax(dim=1)
            all_preds.extend(preds.cpu().numpy().tolist())
            all_labels.extend(labels.cpu().numpy().tolist())
    acc = float(np.mean(np.array(all_preds) == np.array(all_labels)))
    macro_f1 = float(f1_score(all_labels, all_preds, average="macro", zero_division=0))
    cm = confusion_matrix(all_labels, all_preds)
    report = classification_report(all_labels, all_preds, zero_division=0)
    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
    }


# =========================================================
# 训练主循环
# =========================================================

def train(cfg: dict, args):
    if getattr(args, "smoke", False):
        device = torch.device("cpu")
        logger.warning("⚠️ --smoke 烟测模式：强制 CPU，不占 GPU 卡槽，结果不报正式数字。")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"使用设备: {device}")

    project_root = Path(__file__).parent.parent
    log_dir = project_root / cfg.get("log_dir", "log")
    checkpoint_dir = project_root / cfg.get("checkpoint_dir", "log/checkpoints")
    log_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    split_csv_dir = Path(args.split_csv_dir)

    # 图像变换
    mean = cfg["normalize_mean"]
    std = cfg["normalize_std"]
    img_size = cfg["image_size"]

    train_transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.RandomHorizontalFlip() if cfg.get("aug_hflip", True) else transforms.Lambda(lambda x: x),
        transforms.RandomRotation(degrees=cfg.get("aug_rotation_degrees", 15)),
        # 禁 vertical flip（颅脑方向）
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])
    eval_transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])

    # Dataset / DataLoader
    train_ds = MRIDataset(split_csv_dir / "train.csv", transform=train_transform)
    val_ds = MRIDataset(split_csv_dir / "val.csv", transform=eval_transform)
    test_ds = MRIDataset(split_csv_dir / "test.csv", transform=eval_transform)

    # 验证类别一致性
    assert train_ds.class_to_idx == val_ds.class_to_idx == test_ds.class_to_idx, \
        "train/val/test 类别 mapping 不一致，请检查 split csv。"
    class_to_idx = train_ds.class_to_idx
    num_classes = cfg.get("num_classes", 4)

    num_workers = cfg.get("num_workers", 0)
    pin_memory = cfg.get("pin_memory", False)  # Windows spawn 不支持 pin_memory=True
    batch_size = cfg.get("batch_size", 32)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True,
        num_workers=num_workers, pin_memory=pin_memory,
        multiprocessing_context="spawn" if num_workers > 0 else None,
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False,
        num_workers=num_workers, pin_memory=pin_memory,
        multiprocessing_context="spawn" if num_workers > 0 else None,
    )
    test_loader = DataLoader(
        test_ds, batch_size=batch_size, shuffle=False,
        num_workers=num_workers, pin_memory=pin_memory,
        multiprocessing_context="spawn" if num_workers > 0 else None,
    )

    logger.info(f"train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}")

    # 模型
    backbone_name = cfg.get("backbone", "resnet50")
    pretrained = cfg.get("pretrained", True)
    model = build_backbone(backbone_name, num_classes, pretrained)
    model = model.to(device)

    # 类不均衡处理
    if cfg.get("use_class_weight", True):
        class_weights = compute_class_weights(split_csv_dir / "train.csv", class_to_idx, device)
        criterion = nn.CrossEntropyLoss(weight=class_weights)
    else:
        criterion = nn.CrossEntropyLoss()

    # 优化器（researcher T3: Adam lr=1e-4）
    lr = cfg.get("lr", 1e-4)
    optimizer_name = cfg.get("optimizer", "adam").lower()
    if optimizer_name == "adam":
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    elif optimizer_name == "adamw":
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    elif optimizer_name == "sgd":
        optimizer = torch.optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=1e-4)
    else:
        raise ValueError(f"未知 optimizer: {optimizer_name}")

    # Scheduler
    epochs = cfg.get("epochs", 50)
    scheduler_name = cfg.get("scheduler", "cosine")
    if scheduler_name == "cosine":
        scheduler = CosineAnnealingLR(optimizer, T_max=epochs)
    else:
        scheduler = None

    # 训练循环
    best_val_f1 = -1.0
    best_ckpt_path = checkpoint_dir / f"{backbone_name}_seed{args.seed}_best.pt"
    history = []

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for imgs, labels in train_loader:
            imgs, labels = imgs.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(imgs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * imgs.size(0)

        if scheduler is not None:
            scheduler.step()

        train_loss = running_loss / len(train_ds)
        val_metrics = evaluate(model, val_loader, device)
        logger.info(
            f"Epoch {epoch}/{epochs} | train_loss={train_loss:.4f} "
            f"| val_acc={val_metrics['accuracy']:.4f} "
            f"| val_macro_f1={val_metrics['macro_f1']:.4f}"
        )

        history.append({
            "epoch": epoch,
            "train_loss": train_loss,
            "val_accuracy": val_metrics["accuracy"],
            "val_macro_f1": val_metrics["macro_f1"],
        })

        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            torch.save(model.state_dict(), best_ckpt_path)
            logger.info(f"  -> best val macro_f1={best_val_f1:.4f}，checkpoint 已存 {best_ckpt_path}")

    # 加载最优 checkpoint 做 test
    model.load_state_dict(torch.load(best_ckpt_path, map_location=device))
    test_metrics = evaluate(model, test_loader, device)
    logger.info(
        f"\n=== TEST RESULTS ===\n"
        f"  backbone:  {backbone_name}\n"
        f"  test acc:  {test_metrics['accuracy']:.4f}\n"
        f"  macro_F1:  {test_metrics['macro_f1']:.4f}\n"
        f"  confusion matrix:\n{np.array(test_metrics['confusion_matrix'])}\n"
        f"  report:\n{test_metrics['classification_report']}"
    )

    # 写结果 csv
    results_csv = project_root / cfg.get("results_csv", "log/classifier_results.csv")
    row = {
        "backbone": backbone_name,
        "seed": args.seed,
        "epochs": epochs,
        "split_mode": cfg.get("split_mode", "unknown"),
        "test_accuracy": test_metrics["accuracy"],
        "test_macro_f1": test_metrics["macro_f1"],
        "best_val_macro_f1": best_val_f1,
        "checkpoint": str(best_ckpt_path),
        "timestamp": datetime.now().isoformat(),
    }
    df_result = pd.DataFrame([row])
    if results_csv.exists():
        df_result.to_csv(results_csv, mode="a", header=False, index=False)
    else:
        df_result.to_csv(results_csv, index=False)
    logger.info(f"结果 csv 已写 -> {results_csv}")

    # state.json
    state_path = project_root / cfg.get("state_json", "log/classifier_state.json")
    state = {
        "script": "train_classifier.py",
        "timestamp": datetime.now().isoformat(),
        "backbone": backbone_name,
        "seed": args.seed,
        "epochs": epochs,
        "split_mode": cfg.get("split_mode", "unknown"),
        "test_accuracy": test_metrics["accuracy"],
        "test_macro_f1": test_metrics["macro_f1"],
        "confusion_matrix": test_metrics["confusion_matrix"],
        "best_ckpt": str(best_ckpt_path),
        "history": history,
        "config": cfg,
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info(f"state.json 已写 -> {state_path}")

    return test_metrics, str(best_ckpt_path)


# =========================================================
# 入口（Windows spawn 守卫）
# =========================================================

def main():
    parser = argparse.ArgumentParser(description="WaveFidBench train_classifier.py")
    parser.add_argument("--config", required=True, help="YAML config 路径")
    parser.add_argument("--data_root", required=True, help="数据根目录（4 类子文件夹）")
    parser.add_argument(
        "--split_csv_dir",
        default=None,
        help="split csv 目录（train.csv/val.csv/test.csv），默认从 config 读",
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子（s1=42/s2=1/s3=7）")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="烟测模式：强制 CPU（不占 GPU 卡槽），仅验工程管道跑通。结果不报正式数字。",
    )
    args = parser.parse_args()

    # 设置全局 seed
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # split_csv_dir 优先用命令行传入，否则从 config 推导
    if args.split_csv_dir is None:
        project_root = Path(__file__).parent.parent
        args.split_csv_dir = str(project_root / cfg.get("split_csv_dir", "log/splits"))

    logger.info(f"split_csv_dir = {args.split_csv_dir}")
    train(cfg, args)


if __name__ == "__main__":
    main()
