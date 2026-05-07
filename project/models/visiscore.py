"""VisiScore-Net: lightweight multi-head IQA network for skin images."""
import timm
import torch
import torch.nn as nn


class VisiScoreNet(nn.Module):
    def __init__(self, backbone: str = "mobilenetv3_large_100", pretrained: bool = True, num_dims: int = 5):
        super().__init__()
        self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0)
        with torch.no_grad():
            feat_dim = self.backbone(torch.zeros(1, 3, 224, 224)).shape[1]
        self.heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(feat_dim, 128),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(128, 1),
                nn.Sigmoid(),
            )
            for _ in range(num_dims)
        ])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.backbone(x)
        scores = torch.cat([head(feat) for head in self.heads], dim=1)
        return scores  # (B, num_dims)

    def forward_features(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (features, q_vector) for Q-VIB encoder reuse.

        features: backbone pooled vector (B, feat_dim)
        q_vector: quality scores (B, num_dims), values in [0, 1]
        """
        feat = self.backbone(x)
        scores = torch.cat([head(feat) for head in self.heads], dim=1)
        return feat, scores
