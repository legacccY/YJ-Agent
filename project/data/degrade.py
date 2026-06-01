"""图像退化模拟：生成 3 档（轻/中/重）低质量版本"""
import random
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

# 3 档退化强度配置
DEGRADATION_LEVELS = {
    "light": {
        "blur_ksize": (3, 3),
        "blur_sigma": 0.8,
        "brightness_range": (0.85, 1.0),
        "jpeg_quality": (75, 90),
        "crop_ratio": (0.90, 1.0),
        "color_shift": 0.05,
    },
    "medium": {
        "blur_ksize": (5, 5),
        "blur_sigma": 1.5,
        "brightness_range": (0.65, 0.85),
        "jpeg_quality": (50, 74),
        "crop_ratio": (0.75, 0.89),
        "color_shift": 0.12,
    },
    "heavy": {
        "blur_ksize": (9, 9),
        "blur_sigma": 2.5,
        "brightness_range": (0.40, 0.64),
        "jpeg_quality": (20, 49),
        "crop_ratio": (0.55, 0.74),
        "color_shift": 0.22,
    },
}

# 每种退化类型的激活概率（独立应用，可叠加）
DEGRADATION_PROBS = {
    "blur": 0.7,
    "brightness": 0.6,
    "jpeg": 0.8,
    "crop": 0.5,
    "color_shift": 0.5,
}


def apply_gaussian_blur(img: np.ndarray, cfg: dict) -> np.ndarray:
    return cv2.GaussianBlur(img, cfg["blur_ksize"], cfg["blur_sigma"])


def apply_brightness(img: np.ndarray, cfg: dict) -> np.ndarray:
    factor = random.uniform(*cfg["brightness_range"])
    img_f = img.astype(np.float32) * factor
    return np.clip(img_f, 0, 255).astype(np.uint8)


def apply_jpeg_compression(img: np.ndarray, cfg: dict) -> np.ndarray:
    quality = random.randint(*cfg["jpeg_quality"])
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, buf = cv2.imencode(".jpg", img, encode_param)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def apply_random_crop(img: np.ndarray, cfg: dict, target_size: int = 256) -> np.ndarray:
    h, w = img.shape[:2]
    ratio = random.uniform(*cfg["crop_ratio"])
    crop_h, crop_w = int(h * ratio), int(w * ratio)
    y = random.randint(0, h - crop_h)
    x = random.randint(0, w - crop_w)
    cropped = img[y : y + crop_h, x : x + crop_w]
    return cv2.resize(cropped, (target_size, target_size), interpolation=cv2.INTER_LINEAR)


def apply_color_shift(img: np.ndarray, cfg: dict) -> np.ndarray:
    shift = cfg["color_shift"]
    img_f = img.astype(np.float32)
    for c in range(3):
        delta = random.uniform(-shift * 255, shift * 255)
        img_f[:, :, c] = np.clip(img_f[:, :, c] + delta, 0, 255)
    return img_f.astype(np.uint8)


def degrade_image(
    img: np.ndarray,
    level: str,
    target_size: int = 256,
    crop_prob: float | None = None,
) -> np.ndarray:
    """对单张图片应用退化，返回退化后的图片。

    crop_prob: 随机裁剪激活概率。None=用默认 DEGRADATION_PROBS["crop"]。
    设 0 = 关闭裁剪（enhance 配对数据用，保像素对齐，不强迫模型 hallucinate 被裁组织）。
    裁剪属取景错位，归 Theorem 2 query-for-retake 通道，不属增强任务。
    """
    cfg = DEGRADATION_LEVELS[level]
    p_crop = DEGRADATION_PROBS["crop"] if crop_prob is None else crop_prob
    result = img.copy()

    if random.random() < DEGRADATION_PROBS["blur"]:
        result = apply_gaussian_blur(result, cfg)
    if random.random() < DEGRADATION_PROBS["brightness"]:
        result = apply_brightness(result, cfg)
    if random.random() < DEGRADATION_PROBS["color_shift"]:
        result = apply_color_shift(result, cfg)
    if random.random() < p_crop:
        result = apply_random_crop(result, cfg, target_size)
    else:
        result = cv2.resize(result, (target_size, target_size), interpolation=cv2.INTER_LINEAR)
    if random.random() < DEGRADATION_PROBS["jpeg"]:
        result = apply_jpeg_compression(result, cfg)

    return result


def process_dataset(
    src_dir: Path,
    out_dir: Path,
    levels: list[str] | None = None,
    target_size: int = 256,
    seed: int = 42,
) -> None:
    """批量处理整个数据集，按 level 生成子目录"""
    if levels is None:
        levels = list(DEGRADATION_LEVELS.keys())

    random.seed(seed)
    np.random.seed(seed)

    image_paths = sorted(src_dir.glob("**/*.jpg")) + sorted(src_dir.glob("**/*.png"))
    if not image_paths:
        raise FileNotFoundError(f"在 {src_dir} 中未找到图片")

    print(f"[INFO] 找到 {len(image_paths)} 张原始图片，生成 {levels} 档退化")

    for level in levels:
        level_dir = out_dir / level
        level_dir.mkdir(parents=True, exist_ok=True)

        for img_path in tqdm(image_paths, desc=f"{level} 档退化"):
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            degraded = degrade_image(img, level, target_size)
            out_path = level_dir / img_path.name
            cv2.imwrite(str(out_path), degraded)

    print(f"[INFO] 退化完成，输出到 {out_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, required=True, help="原始图片目录")
    parser.add_argument("--out", type=Path, default=Path("D:/YJ-Agent/data/paired_dataset"))
    parser.add_argument("--levels", nargs="+", default=["light", "medium", "heavy"])
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()

    process_dataset(args.src, args.out, args.levels, args.size)
