"""E10 登录节点 CPU smoke: 6 baseline 各 build() 加载权重(strict=True) + forward 256->256.
strict=True 下 arch/权重 key 不匹配会立即抛错 -> 验证 vendor arch 正确 + 权重完整.
range 偏离 [0,1] 太多提示权重可能损坏/镜像不对(尤其 Uformer 第三方 HF 镜像)."""
import importlib
import sys

import torch

sys.path.insert(0, ".")
WEIGHTS_DIR = "/gpfs/work/bio/jiayu2403/visienhance/checkpoints/baselines"
device = torch.device("cpu")
x = torch.rand(1, 3, 256, 256)

for m in ["restormer", "nafnet", "mirnetv2", "swinir", "uformer", "realesrgan"]:
    try:
        mod = importlib.import_module(f"baselines.run_{m}_inference")
        obj = mod.build(device, WEIGHTS_DIR)
        with torch.no_grad():
            o = obj(x, None)
        ok = tuple(o.shape) == (1, 3, 256, 256)
        print(f"{'OK ' if ok else 'BAD'} {m:11s} {mod.DISPLAY_NAME:24s} "
              f"out={tuple(o.shape)} range=[{o.min():.3f},{o.max():.3f}]")
    except Exception as e:
        print(f"FAIL {m:11s} {type(e).__name__}: {str(e)[:180]}")
