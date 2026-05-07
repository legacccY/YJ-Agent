"""Agent 工具定义：将阶段三/四模型封装为标准化可调用工具。

工具列表:
  quality_assess(image_rgb) -> QualityResult
  extract_features(image_rgb) -> FeaturesResult
  triage(features) -> TriageResult
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import transforms
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from models.visiscore import VisiScoreNet
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.feature_extractor import extract_abcd

# ── Constants ─────────────────────────────────────────────────────────────────
QUALITY_DIMS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
QUALITY_THRESHOLD = 0.30   # 用于标记最差的维度（问题标签），不用于 is_acceptable 判断
OVERALL_THRESHOLD = 0.50   # 均值低于此值 → 整体质量差，触发引导

IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

VISISCORE_CKPT = "D:/YJ-Agent/checkpoints/best_visiscore.pth"
QAD_CKPT       = "D:/YJ-Agent/checkpoints/efnet/best_qad.pth"

_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
])


# ── Result dataclasses ────────────────────────────────────────────────────────
@dataclass
class QualityResult:
    scores: dict[str, float]   # 各维度分数 [0,1]
    overall: float             # 均值
    issues: list[str]          # 低于阈值的维度名称
    is_acceptable: bool        # True = 质量达标


@dataclass
class FeaturesResult:
    abcd: np.ndarray           # (4,)  [asymmetry, border, color, diameter]
    q_vector: np.ndarray       # (5,)  来自 VisiScore-Net
    efnet_feat: np.ndarray     # (1280,)
    mask: np.ndarray           # (H, W) bool


@dataclass
class TriageResult:
    malignancy_prob: float         # 恶性概率 [0,1]
    uncertainty: float             # 预测熵（不确定性）
    abcd_values: dict[str, float]  # ABCD 各维度值
    recommendation: str            # 分诊建议
    urgency: str                   # "low" / "medium" / "high"
    disclaimer: str                # 免责声明


# ── Model registry (lazy singleton) ─────────────────────────────────────────
class ModelRegistry:
    """延迟加载所有推理模型，确保只初始化一次。"""

    _instance: Optional["ModelRegistry"] = None

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._visiscore: Optional[VisiScoreNet] = None
        self._efnet: Optional[torch.nn.Module] = None
        self._encoder: Optional[QVIBEncoder] = None
        self._classifier: Optional[QADClassifier] = None

    @classmethod
    def get(cls) -> "ModelRegistry":
        if cls._instance is None:
            cls._instance = ModelRegistry()
        return cls._instance

    @property
    def visiscore(self) -> VisiScoreNet:
        if self._visiscore is None:
            model = VisiScoreNet(pretrained=False)
            ckpt = torch.load(VISISCORE_CKPT, map_location=self.device)
            state_dict = ckpt.get("model", ckpt)
            model.load_state_dict(state_dict)
            model.to(self.device).eval()
            self._visiscore = model
        return self._visiscore

    @property
    def efnet(self) -> torch.nn.Module:
        if self._efnet is None:
            model = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
            model.classifier = torch.nn.Identity()
            model.to(self.device).eval()
            self._efnet = model
        return self._efnet

    def _load_qad(self):
        if self._encoder is not None:
            return
        ckpt = torch.load(QAD_CKPT, map_location=self.device)
        self._encoder = QVIBEncoder(
            abcd_dim=4, q_dim=5,
            d_model=128, n_heads=4, latent_dim=64, efnet_dim=1280,
        ).to(self.device).eval()
        self._classifier = QADClassifier(
            latent_dim=64, hidden_dim=128, num_classes=2,
        ).to(self.device).eval()
        self._encoder.load_state_dict(ckpt["encoder"])
        self._classifier.load_state_dict(ckpt["classifier"])

    @property
    def encoder(self) -> QVIBEncoder:
        self._load_qad()
        return self._encoder

    @property
    def classifier(self) -> QADClassifier:
        self._load_qad()
        return self._classifier


# ── Tool functions ────────────────────────────────────────────────────────────

def quality_assess(image_rgb: np.ndarray) -> QualityResult:
    """评估皮肤图片质量。

    Args:
        image_rgb: RGB 图片，uint8，任意尺寸。
    Returns:
        QualityResult，包含各维度得分和存在的质量问题。
    """
    reg = ModelRegistry.get()
    img = cv2.resize(image_rgb, (IMG_SIZE, IMG_SIZE))
    tensor = _TRANSFORM(img).unsqueeze(0).to(reg.device)

    with torch.no_grad():
        scores = reg.visiscore(tensor)[0].cpu().numpy()   # (5,)

    score_dict = {dim: float(scores[i]) for i, dim in enumerate(QUALITY_DIMS)}
    overall = float(scores.mean())
    # issues 标记最差的维度，用于选问题；is_acceptable 只看整体均值
    issues = sorted(score_dict, key=lambda d: score_dict[d])[:2]  # 最低两个维度
    issues = [d for d in issues if score_dict[d] < overall]        # 仅保留低于均值的
    is_acceptable = overall >= OVERALL_THRESHOLD

    return QualityResult(
        scores=score_dict,
        overall=overall,
        issues=issues,
        is_acceptable=is_acceptable,
    )


def _otsu_mask(image_bgr: np.ndarray) -> np.ndarray:
    """OTSU 快速分割（<1ms），用于实时 ABCD 提取。"""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    if mask.sum() < 0.02 * mask.size:
        H, W = mask.shape
        mask = np.zeros((H, W), dtype=np.uint8)
        cv2.ellipse(mask, (W // 2, H // 2), (W // 3, H // 3), 0, 0, 360, 255, -1)
    return mask.astype(bool)


def extract_features(image_rgb: np.ndarray) -> FeaturesResult:
    """提取 ABCD 特征 + EfficientNet-B0 特征 + VisiScore q 向量。

    Args:
        image_rgb: RGB 图片，uint8。
    Returns:
        FeaturesResult
    """
    reg = ModelRegistry.get()

    img_resized = cv2.resize(image_rgb, (IMG_SIZE, IMG_SIZE))
    img_bgr = cv2.cvtColor(img_resized, cv2.COLOR_RGB2BGR)

    # ABCD via OTSU mask
    mask = _otsu_mask(img_bgr)
    abcd = extract_abcd(img_bgr, mask)   # (4,)

    tensor = _TRANSFORM(img_resized).unsqueeze(0).to(reg.device)

    with torch.no_grad():
        # VisiScore q_vector
        _, q_vector_t = reg.visiscore.forward_features(tensor)
        q_vector = q_vector_t[0].cpu().numpy()   # (5,)

        # EfficientNet features
        efnet_feat = reg.efnet(tensor)[0].cpu().numpy()   # (1280,)

    return FeaturesResult(
        abcd=abcd,
        q_vector=q_vector,
        efnet_feat=efnet_feat,
        mask=mask,
    )


def triage(features: FeaturesResult, n_mc: int = 20) -> TriageResult:
    """MC Dropout 推断，给出恶性概率和分诊建议（非诊断）。

    Args:
        features: extract_features 的输出。
        n_mc: Monte Carlo 采样次数。
    Returns:
        TriageResult
    """
    reg = ModelRegistry.get()

    abcd_t = torch.tensor(features.abcd, dtype=torch.float32).unsqueeze(0).to(reg.device)
    q_t    = torch.tensor(features.q_vector, dtype=torch.float32).unsqueeze(0).to(reg.device)
    ef_t   = torch.tensor(features.efnet_feat, dtype=torch.float32).unsqueeze(0).to(reg.device)

    probs_list = []
    with torch.no_grad():
        mu, log_sigma_sq = reg.encoder(abcd_t, q_t, efnet_feat=ef_t)
        for _ in range(n_mc):
            z = reg.encoder.reparameterize(mu, log_sigma_sq)
            logits = reg.classifier(z)
            probs_list.append(F.softmax(logits, dim=-1))

    mean_probs = torch.stack(probs_list).mean(dim=0)[0]   # (2,)
    entropy = float(-(mean_probs * mean_probs.log().clamp(-20)).sum().item())
    malignancy_prob = float(mean_probs[1].item())

    if malignancy_prob < 0.30:
        urgency = "low"
        recommendation = (
            "综合图片分析，皮损特征属于低风险范围。建议每月自查，"
            "若 3 个月内出现颜色加深、边界扩大或出血，请尽快就诊。"
        )
    elif malignancy_prob < 0.60:
        urgency = "medium"
        recommendation = (
            "皮损存在部分需要关注的特征，建议在 2 周内前往皮肤科进行专业检查，"
            "由医生通过皮肤镜进一步评估。"
        )
    else:
        urgency = "high"
        recommendation = (
            "皮损特征显示较高风险信号，建议尽快（1 周内）到皮肤科就诊，"
            "进行皮肤镜检查或活检确认。"
        )

    return TriageResult(
        malignancy_prob=malignancy_prob,
        uncertainty=entropy,
        abcd_values={
            "asymmetry": float(features.abcd[0]),
            "border":    float(features.abcd[1]),
            "color":     float(features.abcd[2]),
            "diameter":  float(features.abcd[3]),
        },
        recommendation=recommendation,
        urgency=urgency,
        disclaimer=(
            "⚠️ 本系统仅供辅助参考，不构成医疗诊断。"
            "请务必咨询执业皮肤科医生获取专业意见。"
        ),
    )
