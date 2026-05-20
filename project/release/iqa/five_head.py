"""5-Head IQA module: predicts 5 quality dimensions from a dermoscopy image."""
import torch
import torch.nn as nn
import timm
import numpy as np
from PIL import Image
import torchvision.transforms as T

QUALITY_DIMS = ["sharpness", "brightness", "completeness", "color_temperature", "contrast"]

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]


class FiveHeadIQA(nn.Module):
    """EfficientNet-B0 backbone with 5 linear regression heads.

    Each head predicts one quality dimension in [0, 1]:
      q1: sharpness, q2: brightness, q3: completeness,
      q4: color_temperature, q5: contrast.
    Mean scalar: qbar = (q1+...+q5) / 5.
    """

    def __init__(self, pretrained: bool = True):
        super().__init__()
        self.backbone = timm.create_model(
            "efficientnet_b0", pretrained=pretrained, num_classes=0
        )
        feat_dim = self.backbone.num_features
        self.heads = nn.ModuleList([nn.Linear(feat_dim, 1) for _ in range(5)])
        self.transform = T.Compose([
            T.Resize(256),
            T.CenterCrop(224),
            T.ToTensor(),
            T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Returns quality vector [B, 5] clamped to [0, 1]."""
        feats = self.backbone(x)
        scores = torch.cat([h(feats) for h in self.heads], dim=1)
        return scores.clamp(0.0, 1.0)

    @torch.no_grad()
    def predict_image(self, image: Image.Image, device: str = "cpu") -> dict:
        """Predict quality dimensions for a single PIL image."""
        x = self.transform(image).unsqueeze(0).to(device)
        self.to(device).eval()
        q = self(x).squeeze(0).cpu().numpy()
        result = {dim: float(q[i]) for i, dim in enumerate(QUALITY_DIMS)}
        result["qbar"] = float(q.mean())
        return result

    @classmethod
    def from_checkpoint(cls, ckpt_path: str, device: str = "cpu") -> "FiveHeadIQA":
        model = cls(pretrained=False)
        state = torch.load(ckpt_path, map_location=device)
        model.load_state_dict(state["model_state_dict"] if "model_state_dict" in state else state)
        return model.to(device).eval()
