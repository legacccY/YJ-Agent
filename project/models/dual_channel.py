"""Dual-Channel Decision Logic for VisiSkin-Agent.

Two pathways based on input quality q̄:
  A1 (q̄ ≥ 0.60): High quality → Q-VIB diagnosis directly.
  A2 (0.50 ≤ q̄ < 0.60): Near-high quality → diagnosis + light caution message.
  B  (0.35 ≤ q̄ < 0.50): Enhanceable → VisiEnhance-Net → re-assess → diagnose or retake.
  C  (q̄ < 0.35): Too degraded → Agent retake prompt (enhancement pointless).

Special rule: if q3 (completeness) < 0.40, bypass enhancement entirely and go to C.
This implements the irrecoverability analysis: q3 loss is permanent (theory doc §3).
"""

from __future__ import annotations

import torch
import torch.nn as nn


class DualChannelAgent(nn.Module):
    """Orchestrates VisiScore → enhance/diagnose → Agent decision.

    All sub-models passed in must already be on the correct device and in eval mode.

    Args:
        visiscore:   VisiScoreNet (frozen).
        visienhance: VisiEnhanceNet (frozen after training).
        qvib_fn:     Callable(x, q) → (pred_prob, entropy). Can be None for stub.
        high_thresh:       q̄ threshold for "high quality" (A1).  Default 0.60.
        near_high_thresh:  q̄ threshold for "near-high" (A2).    Default 0.50.
        enhance_thresh:    q̄ threshold for "enhanceable" (B).   Default 0.35.
        enhanced_thresh:   q̄ after enhancement to proceed (B success). Default 0.50.
        completeness_min:  Min q3 to allow enhancement. Default 0.40.
    """

    def __init__(
        self,
        visiscore: nn.Module,
        visienhance: nn.Module,
        qvib_fn=None,
        high_thresh: float = 0.60,
        near_high_thresh: float = 0.50,
        enhance_thresh: float = 0.35,
        enhanced_thresh: float = 0.50,
        completeness_min: float = 0.40,
    ):
        super().__init__()
        self.visiscore = visiscore
        self.visienhance = visienhance
        self.qvib_fn = qvib_fn

        self.high_thresh = high_thresh
        self.near_high_thresh = near_high_thresh
        self.enhance_thresh = enhance_thresh
        self.enhanced_thresh = enhanced_thresh
        self.completeness_min = completeness_min

    @torch.no_grad()
    def forward(self, x: torch.Tensor) -> dict:
        """Process a single image (or batch) through the dual-channel pipeline.

        Args:
            x: Image tensor [B, 3, H, W] in [0, 1].

        Returns dict with keys:
            pathway:          'A1' | 'A2' | 'B_success' | 'B_fail' | 'C'
            q_original:       Quality vector [B, 5]
            q_enhanced:       Quality vector after enhancement, or None
            x_enhanced:       Enhanced image, or None
            pred_prob:        Malignancy probability [B], or None
            entropy:          Prediction entropy [B], or None
            agent_message:    Guidance string for retake cases
        """
        q = self.visiscore(x)           # [B, 5]
        q_bar = q.mean(dim=-1)          # [B]
        q3 = q[:, 2]                    # completeness dimension

        out = {
            "q_original": q,
            "q_enhanced": None,
            "x_enhanced": None,
            "pred_prob": None,
            "entropy": None,
            "agent_message": None,
        }

        # Batch-level decision (uses mean q̄ for simplicity; per-sample in production)
        mean_qbar = q_bar.mean().item()
        mean_q3 = q3.mean().item()

        if mean_qbar >= self.high_thresh:
            out["pathway"] = "A1"
            out.update(self._diagnose(x, q))

        elif mean_qbar >= self.near_high_thresh:
            out["pathway"] = "A2"
            out.update(self._diagnose(x, q))
            out["agent_message"] = (
                "图像质量略低，建议在良好光线下重新拍摄以获得更准确的结果。"
            )

        elif mean_qbar >= self.enhance_thresh and mean_q3 >= self.completeness_min:
            # Channel B: attempt enhancement
            x_enh = self.visienhance(x, q)
            q_enh = self.visiscore(x_enh)
            q_bar_enh = q_enh.mean(dim=-1).mean().item()

            out["x_enhanced"] = x_enh
            out["q_enhanced"] = q_enh

            if q_bar_enh >= self.enhanced_thresh:
                out["pathway"] = "B_success"
                out.update(self._diagnose(x_enh, q_enh))
                out["agent_message"] = "图像已自动优化，诊断基于增强后图像。"
            else:
                out["pathway"] = "B_fail"
                out["agent_message"] = self._retake_guidance(q, reason="enhance_failed")

        else:
            out["pathway"] = "C"
            out["agent_message"] = self._retake_guidance(q, reason="too_low")

        return out

    def _diagnose(self, x: torch.Tensor, q: torch.Tensor) -> dict:
        if self.qvib_fn is None:
            return {"pred_prob": None, "entropy": None}
        pred_prob, entropy = self.qvib_fn(x, q)
        return {"pred_prob": pred_prob, "entropy": entropy}

    @staticmethod
    def _retake_guidance(q: torch.Tensor, reason: str) -> str:
        q_mean = q.mean(dim=0)  # [5]: sharpness/brightness/completeness/color/contrast
        issues = []
        if q_mean[0] < 0.5:
            issues.append("对焦不清晰（请保持手机稳定）")
        if q_mean[1] < 0.5:
            issues.append("光线不足（请移至自然光线充足的地方）")
        if q_mean[2] < 0.4:
            issues.append("病灶未完整在画面内（请靠近并居中拍摄）")
        if q_mean[3] < 0.5:
            issues.append("色彩偏色（请避免强烈的有色光源）")
        if q_mean[4] < 0.5:
            issues.append("对比度不足（请在均匀光线下拍摄）")

        if not issues:
            issues = ["图像整体质量过低"]

        prefix = "图像增强后仍不达标，" if reason == "enhance_failed" else ""
        return prefix + "请重新拍摄。建议改善：" + "；".join(issues) + "。"
