# NCA-JEPA 集成 smoke：验主线接线（helper.init_model NCA 分支 + NIH dataset），不启训练。
# 跑：cd NCA-JEPA && python smoke_integration.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ijepa'))
import torch
from src.helper import init_model

DEV = torch.device('cpu')
DATA_ROOT = os.path.join(os.path.dirname(__file__), 'data', 'nih_cxr14')

print('=== [1] init_model scp_nca (A2) ===')
enc, pred = init_model(device=DEV, patch_size=16, crop_size=224, model_name='vit_small',
                       pred_emb_dim=384, predictor_type='scp_nca', nca_steps=16,
                       nca_hidden=128, fire_rate=0.5, stabilize=True,
                       deterministic_fire=True, fire_seed=42)
np_pred = sum(p.numel() for p in pred.parameters())
print(f'  encoder={type(enc).__name__} predictor={type(pred).__name__} '
      f'predictor_params={np_pred} num_patches={enc.patch_embed.num_patches}')
assert pred.__class__.__name__ == 'NCAPredictor', 'A2 没接到 NCA predictor!'

print('=== [2] predictor forward (mask 玩具) ===')
B, N = 2, enc.patch_embed.num_patches  # 196
D = enc.embed_dim
n_ctx, n_pred = 100, 30
x = torch.randn(B, n_ctx, D)
masks_x = [torch.randint(0, N, (B, n_ctx))]
masks = [torch.randint(0, N, (B, n_pred))]
out = pred(x, masks_x, masks)
print(f'  forward out shape={tuple(out.shape)} (期望 [{len(masks)*B}, {n_pred}, {D}])')
assert out.shape == (len(masks) * B, n_pred, D)

print('=== [3] init_model vit (官方回退不破) ===')
enc2, pred2 = init_model(device=DEV, model_name='vit_small', predictor_type='vit', pred_emb_dim=384)
print(f'  predictor={type(pred2).__name__} (期望 VisionTransformerPredictor)')

print('=== [4] NIH dataset 取图 ===')
from src.datasets.nih_cxr14 import NIHChestXray14
import torchvision.transforms as T
tf = T.Compose([T.Resize((224, 224)), T.ToTensor()])
subset = os.path.join(DATA_ROOT, 'splits', 'pretrain_10k.txt')
ds = NIHChestXray14(root=DATA_ROOT, image_folder='images-224/images-224', transform=tf, subset_file=subset)
img, label = ds[0]
print(f'  dataset_len={len(ds)} img_shape={tuple(img.shape)} (期望 3x224x224) label={label}')
assert img.shape[0] == 3, '灰度没转 3 通道!'

print('\nALL SMOKE PASS [OK]')
