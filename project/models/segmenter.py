"""MobileSAM segmentation wrapper.

Provides a unified interface: image -> binary lesion mask.
Uses automatic (grid-point) prompting for zero-shot lesion segmentation.
"""

import numpy as np
import torch
import torch.nn as nn
from pathlib import Path


class MobileSAMSegmenter(nn.Module):
    """Zero-shot lesion segmenter based on MobileSAM.

    Args:
        checkpoint: Path to mobile_sam.pt weights.
        device: torch device.
        points_per_side: Grid density for automatic mask generation.
        score_threshold: Minimum IoU score to accept a mask.
    """

    def __init__(
        self,
        checkpoint: str | Path = "D:/YJ-Agent/checkpoints/mobile_sam.pt",
        device: str | torch.device = "cuda",
        points_per_side: int = 16,
        score_threshold: float = 0.8,
    ):
        super().__init__()
        self.device = torch.device(device)
        self.score_threshold = score_threshold

        from mobile_sam import sam_model_registry, SamAutomaticMaskGenerator

        sam = sam_model_registry["vit_t"](checkpoint=str(checkpoint))
        sam.to(self.device)
        sam.eval()

        self._mask_gen = SamAutomaticMaskGenerator(
            model=sam,
            points_per_side=points_per_side,
            pred_iou_thresh=score_threshold,
            min_mask_region_area=100,
        )

    @torch.no_grad()
    def forward(self, image_np: np.ndarray) -> np.ndarray:
        """Segment lesion region.

        Args:
            image_np: RGB image, shape (H, W, 3), dtype uint8.
        Returns:
            mask: Binary mask, shape (H, W), dtype bool.
                  If no mask passes threshold, returns center-crop mask.
        """
        masks = self._mask_gen.generate(image_np)

        if not masks:
            return self._center_mask(image_np.shape[:2])

        # Pick the largest high-confidence mask (lesion tends to be the dominant region)
        masks = sorted(masks, key=lambda m: m["area"], reverse=True)
        best = masks[0]["segmentation"]  # (H, W) bool
        return best.astype(bool)

    @staticmethod
    def _center_mask(shape: tuple[int, int], fraction: float = 0.5) -> np.ndarray:
        """Fallback: circular mask centered in the image."""
        H, W = shape
        cy, cx = H // 2, W // 2
        ry, rx = int(H * fraction / 2), int(W * fraction / 2)
        y, x = np.ogrid[:H, :W]
        mask = ((y - cy) / ry) ** 2 + ((x - cx) / rx) ** 2 <= 1
        return mask
