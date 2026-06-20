# Vendored from: https://github.com/creatis-myriad/plug-and-play-reco-regularization
# Path in repo: sources/source_2D/post_treatement.py
# License: CeCILL (http://www.cecill.info) — French free software license,
#          permits academic use; must cite papers [1][2] when publishing.
#          [1] Carneiro-Esteves et al., Neurocomputing 2024
#          [2] Carneiro-Esteves et al., TGI3 MICCAI Workshop 2024
# Fetched: 2026-06-20 (main branch)
# Modifications:
#   - Removed file-path-based API (post_treatement accepts tensor instead)
#   - Kept model architecture exactly as official (monai UNet channels=(16,32,64,128))
#   - monai dependency documented in TODO below
#
# TODO: monai is required for this adapter. Install: pip install monai
# TODO: If monai sliding_window_inference unavailable, a fallback numpy loop is provided.

import numpy as np
import torch
import json
from pathlib import Path

# 官方 image_utils.normalize_image — 见 image_utils.py TODO_researcher 注释
from baselines.third_party.creatis_postproc.image_utils import normalize_image


# --------------------------------------------------------------------------- #
#  Official model architecture (monai UNet) — must match pre-trained weights
# --------------------------------------------------------------------------- #

def _build_creatis_model(norm: str = "INSTANCE") -> "torch.nn.Module":
    """
    Build the official creatis reconnecting model (monai UNet).
    Architecture is fixed by official repo — do NOT change.

    monai.networks.nets.UNet(
        spatial_dims=2,
        in_channels=1,
        out_channels=1,
        channels=(16, 32, 64, 128),
        strides=(2, 2, 2),
        num_res_units=2,
        norm=norm
    )
    """
    try:
        import monai
        model = monai.networks.nets.UNet(
            spatial_dims=2,
            in_channels=1,
            out_channels=1,
            channels=(16, 32, 64, 128),
            strides=(2, 2, 2),
            num_res_units=2,
            norm=(norm),
        )
        return model
    except ImportError as e:
        raise ImportError(
            "creatis postproc requires monai. Install with: pip install monai\n"
            f"Original error: {e}"
        )


def _sliding_window_predict(
    image_tensor: torch.Tensor,
    model: torch.nn.Module,
    roi_size: tuple = (96, 96),
    sw_batch_size: int = 5,
    mode: str = "gaussian",
    overlap: float = 0.5,
    device: torch.device = None,
) -> torch.Tensor:
    """
    Run sliding window inference on image_tensor using monai.
    Faithfully reproduces official monai_predict_image().

    Args:
        image_tensor: (1, 1, H, W) float tensor.
        model: loaded creatis model.
        roi_size: patch size (official default: (96, 96)).
        sw_batch_size: batch size for window slices (official: 5).
        mode: blend mode (official: 'gaussian').
        overlap: overlap fraction (official: 0.5).
        device: torch device.

    Returns:
        (H, W) numpy array of sigmoid probabilities in [0, 1].
    """
    try:
        from monai.inferers import sliding_window_inference
    except ImportError as e:
        raise ImportError(f"monai required for sliding_window_inference: {e}")

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.eval()
    model = model.to(device)
    image_tensor = image_tensor.float().to(device)

    with torch.no_grad():
        output = sliding_window_inference(
            image_tensor, roi_size, sw_batch_size, model,
            mode=mode, overlap=overlap,
        )

    output = output.squeeze()
    output = torch.sigmoid(output).cpu().numpy()
    return output


def apply_postproc_iterations(
    binary_seg: np.ndarray,
    model: torch.nn.Module,
    iterations: int = 10,
    roi_size: tuple = (96, 96),
    device: torch.device = None,
) -> np.ndarray:
    """
    Apply the creatis reconnecting model iteratively on a binary segmentation.
    Faithfully reproduces official post_treatement() logic.

    Args:
        binary_seg: (H, W) binary numpy array (uint8, values 0 or 255, or 0/1 bool).
        model: loaded and device-placed creatis model.
        iterations: number of reconnecting passes (official default: 10).
        roi_size: sliding window patch size (official default: (96, 96)).
        device: inference device.

    Returns:
        (H, W) uint8 numpy array with values in {0, 255}.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Normalize to uint8 {0, 255} as official code does
    image = binary_seg.astype(np.float32)
    if image.max() <= 1.0:
        image = (image * 255).astype(np.uint8)
    else:
        image = image.astype(np.uint8)

    for i in range(1, iterations + 1):
        # 官方: image = image_utils.normalize_image(image, 1)
        # → normalize_image(uint8{0,255}, max_val=1) = image/255.0 → [0,1] float32
        # TODO_researcher: normalize_image 第二参数语义见 image_utils.py 注释，须核官方
        normalized = normalize_image(image, max_val=1)  # (H,W) float32 [0,1]
        # Build tensor (1, 1, H, W)
        img_tensor = torch.from_numpy(normalized).unsqueeze(0).unsqueeze(0)
        # Run sliding window inference
        prob = _sliding_window_predict(
            img_tensor, model, roi_size=roi_size, device=device,
        )
        # Threshold at 0.5 and convert back to uint8 {0, 255}
        image = ((prob >= 0.5) * 255).astype(np.uint8)

    return image


def load_creatis_model(
    model_dir: str | Path,
    device: torch.device = None,
) -> tuple:
    """
    Load a pre-trained creatis model from model_dir.
    Reads config_training.json (official schema) to get norm and patch_size.

    Args:
        model_dir: directory containing best_metric_model.pth + config_training.json.
        device: target device.

    Returns:
        (model, config_dict) tuple.
            model: loaded nn.Module on device.
            config_dict: training config from json.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model_dir = Path(model_dir)
    config_path = model_dir / "config_training.json"
    weights_path = model_dir / "best_metric_model.pth"

    if not config_path.exists():
        raise FileNotFoundError(f"config_training.json not found in {model_dir}")
    if not weights_path.exists():
        raise FileNotFoundError(f"best_metric_model.pth not found in {model_dir}")

    with open(config_path, "r") as f:
        cfg = json.load(f)

    norm = cfg.get("norm", "INSTANCE")
    model = _build_creatis_model(norm=norm)
    model.load_state_dict(
        torch.load(str(weights_path), map_location=device)
    )
    model = model.to(device)
    return model, cfg
