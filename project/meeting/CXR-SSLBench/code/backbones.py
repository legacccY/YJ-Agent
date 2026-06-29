# -*- coding: utf-8 -*-
"""
可插拔 backbone 加载器 —— load_backbone(name) -> frozen feature extractor

接口契约：
    fb = load_backbone(name, device='cuda')
    fb.encoder    : nn.Module，已 frozen + eval；forward(x[B,3,H,W]) -> patch tokens [B, num_tokens, D]（无 cls/register token）
    fb.feature_dim: int (vit_base=768 / resnet50=2048)
    fb.num_tokens : int (224/16->196, 518/14->1369, resnet50@224->49 spatial cells, ...)
    fb.transform  : 该 backbone 自己的确定性 eval transform（PIL->tensor[3,H,W]）。datasets.py 用它替换默认 224 transform。
                    None 表示沿用 datasets.build_eval_transform()（CheXWorld 评测路径，224+ImageNet norm）。
    fb.meta       : dict（来源/范式/patch_size/input_size/pool 等）
    fb.forward_tokens(x) -> [B, num_tokens, D]（attentive probe 用，pooling-agnostic）
    fb.forward_pooled(x) -> [B, D]（linear probe 用）。默认 = tokens.mean(1)；
                    个别 backbone 用其规范 pool（rad_dino/imagenet_sup 用 CLS）见 fb.meta['pool']。

⚠️ pooling 一致性 caveat（交 planner/skeptic 确认）：linear-probe 的 pooled 各 backbone 用「该模型规范 pool」
   （MAE/CheXWorld/CheSS/RadJEPA=mean patch token；rad_dino/imagenet_sup=CLS，按 researcher findings 指定）。
   跨 backbone pool 不统一会成为混杂因子；**attentive-probe（token 路径，对所有 backbone 统一）才是公平主对照**。

============================== 已接入 backbone（按范式分类）==============================
| name              | 范式            | 架构          | 输入   | 权重来源                                   | 状态        |
|-------------------|-----------------|---------------|--------|--------------------------------------------|-------------|
| chexworld         | world-model JEPA| ViT-B/16      | 224    | assets/chexworld_pretrained.tar (target_encoder) | ✅已验(烟测过) |
| medical_mae       | MAE             | ViT-B/16      | 224    | Drive 10wqOFCkhyWp6JdSFADrH6Xu9e1am3gXJ (X-rays 0.5M) -> cache/weights/medical_mae_vitb.pth | ✅写好待主线烟测 |
| rad_dino          | DINOv2 蒸馏     | ViT-B/14      | 518    | HF microsoft/rad-dino（自动缓存）          | ✅写好待主线烟测 |
| imagenet_sup_vitb | 监督(off-domain)| ViT-B/16      | 224    | timm vit_base_patch16_224.augreg2_in21k_ft_in1k | ✅写好待主线烟测 |
| radjepa           | I-JEPA          | ViT-B/14      | 224    | HF AIDElab-IITBombay/RadJEPA               | ⚠️未实测，写好优雅降级，主线 curl 验证可下 |
| chess             | 对比(MoCo 式)   | ResNet50      | 224    | Drive 1IfiuQdKV7en9DFaB0NqNdsDkVbdyoVyD -> cache/weights/chess_r50.pth | ✅写好待主线烟测(低优先备选) |

CheXWorld 权重加载逻辑【逐行照搬】CheXWorld repo models/__init__.py::build_transfer_model 的 else 分支
（use_target=True 路径），零偏离。非 timm/HF 模型一律用其官方加载方式 + strict=False，键 remap 见各 _load_*。
重型依赖（timm/torchvision/transformers）一律 loader 内 **惰性 import** —— 缺包时 module 仍可 import，
run_pilot 会把加载异常归类为 SKIP 而非整体崩。
"""
import os
import logging

import torch
import torch.nn as nn

import paths

paths.ensure_repo_on_path()
# 复用 CheXWorld repo 的 ViT 定义（与权重严格对齐，避免自造导致键不匹配）
from models.jepa_vit import vit_tiny, vit_small, vit_base, vit_large, VIT_EMBED_DIMS  # noqa: E402

_VIT_BUILDERS = {
    'vit_tiny': vit_tiny,
    'vit_small': vit_small,
    'vit_base': vit_base,
    'vit_large': vit_large,
}


class FrozenBackbone:
    def __init__(self, encoder, feature_dim, num_tokens, meta,
                 transform=None, pooled_module=None):
        self.encoder = encoder              # 返回 patch tokens [B,T,D]（cls/register 已 strip）
        self.feature_dim = feature_dim
        self.num_tokens = num_tokens
        self.meta = meta
        self.transform = transform          # 该 backbone 专属 eval transform；None=用 datasets 默认
        self._pooled_module = pooled_module  # 可选：返回 [B,D]；None 时默认 tokens.mean(1)

    @torch.no_grad()
    def forward_tokens(self, x):
        """x:[B,3,H,W] -> tokens [B, num_tokens, D]（frozen，eval，no_grad）。"""
        return self.encoder(x)

    @torch.no_grad()
    def forward_pooled(self, x):
        """[B, D]（linear probe 用）。默认 mean over tokens；个别 backbone 用规范 pool（见 meta['pool']）。"""
        if self._pooled_module is not None:
            return self._pooled_module(x)
        return self.encoder(x).mean(dim=1)


def _freeze(module):
    for p in module.parameters():
        p.requires_grad = False
    module.eval()
    return module


# ===========================================================================
# chexworld —— world-model JEPA / ViT-B/16 / 224（逐行照搬 build_transfer_model，已验）
# ===========================================================================
def _load_chexworld(device, model_name='vit_base', input_size=224, patch_size=16,
                    use_target=True, drop_path=0.0):
    """
    照搬 build_transfer_model 的权重加载（use_target=True）。
    tar = torch.save 的 checkpoint dict，含 ckpt['model'] 内 target_encoder.* / encoder.* / predictor.* 键。
    """
    tar = paths.CHEXWORLD_TAR
    assert os.path.exists(tar), f'CheXWorld 权重不存在: {tar}（待主线确认或 HPC 回填 paths.py）'

    encoder = _VIT_BUILDERS[model_name](
        img_size=input_size,
        patch_size=patch_size,
        drop_path_rate=drop_path,
    )
    # [照搬 repo pilot patch] torch 2.6+ 默认 weights_only=True，ckpt 含 argparse.Namespace -> 须 False
    ckpt = torch.load(tar, map_location='cpu', weights_only=False)
    sd = ckpt['model']
    if use_target:
        logging.info('[chexworld] Use Teacher (target_encoder)')
        encoder_sd = {k.replace('target_encoder.', ''): v for k, v in sd.items()
                      if k.startswith('target_encoder.')}
    else:
        logging.info('[chexworld] Use Student (encoder)')
        encoder_sd = {k.replace('encoder.', ''): v for k, v in sd.items()
                      if k.startswith('encoder.')}
    # 224//16==14 且 patch_size==16 -> 无需 pos_embed / patch_embed 插值（与 repo 同条件）
    assert input_size // patch_size == 14, \
        f'非 14x14 grid 需补 pos_embed 插值分支（见 build_transfer_model），当前 {input_size}//{patch_size}'
    assert patch_size == 16, 'patch_size!=16 需补 patch_embed 插值分支（见 build_transfer_model）'
    msg = encoder.load_state_dict(encoder_sd, strict=False)
    logging.info(f'[chexworld] load_state_dict Missing={msg.missing_keys} Unexpected={msg.unexpected_keys}')

    feature_dim = VIT_EMBED_DIMS.get(model_name, 768)
    num_tokens = (input_size // patch_size) ** 2
    encoder = _freeze(encoder.to(device))
    meta = dict(name='chexworld', paradigm='world-model-jepa', source=tar, model=model_name,
                patch_size=patch_size, input_size=input_size, use_target=use_target, pool='mean',
                missing_keys=list(msg.missing_keys), unexpected_keys=list(msg.unexpected_keys))
    # transform=None -> datasets 用默认 CheXWorld 评测 transform（不改既有行为，烟测已过）
    return FrozenBackbone(encoder, feature_dim, num_tokens, meta, transform=None)


# ===========================================================================
# 通用 wrapper module（timm ViT / HF / ResNet -> 统一 [B,T,D] / [B,D]）
# ===========================================================================
class _TimmViTTokens(nn.Module):
    """timm ViT.forward_features -> 去掉 prefix(cls/register) -> patch tokens [B,T,D]。"""
    def __init__(self, model):
        super().__init__()
        self.model = model
        self.num_prefix = int(getattr(model, 'num_prefix_tokens', 1))  # cls=1，含 reg 则更多

    def forward(self, x):
        feats = self.model.forward_features(x)        # [B, prefix+T, D]
        return feats[:, self.num_prefix:]


class _TimmViTCls(nn.Module):
    """timm ViT 取 CLS token [B,D]（监督 ViT 规范 pool）。"""
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model.forward_features(x)[:, 0]   # cls 在 index 0


class _ResNetTokens(nn.Module):
    """torchvision ResNet 卷积主干 -> conv5 特征图 [B,C,h,w] 展平成 [B,h*w,C]（空间 cell 当 token）。"""
    def __init__(self, resnet):
        super().__init__()
        self.body = nn.Sequential(
            resnet.conv1, resnet.bn1, resnet.relu, resnet.maxpool,
            resnet.layer1, resnet.layer2, resnet.layer3, resnet.layer4)

    def forward(self, x):
        f = self.body(x)                              # [B,C,h,w]
        return f.flatten(2).transpose(1, 2).contiguous()  # [B, h*w, C]


# ===========================================================================
# medical_mae —— MAE / ViT-B/16 / 224（X-rays 0.5M pretrain，lambert-x/medical_mae）
#   架构: mae_vit_base_patch16 的 encoder == 标准 ViT-B/16（facebookresearch/mae 风格）
#   加载: ckpt['model'] -> 滤掉 decoder_*/mask_token -> strict=False 灌进 timm vit_base_patch16_224
#   pool: mean patch token（MAE finetune 规范用 global_pool；与 chexworld 一致便于公平）
#   预处理: 同 medical_mae CXR（用 harness CheXWorld 评测 transform：224+ImageNet norm；
#           ⚠️TODO researcher 确认 medical_mae 自家 eval 是否用 chest 专属 mean/std，是则回填）
# ===========================================================================
def _load_medical_mae(device, weights_path=None, model_name='vit_base_patch16_224', input_size=224):
    import timm  # 惰性 import
    wp = weights_path or paths.MEDICAL_MAE_WEIGHTS
    assert os.path.exists(wp), (
        f'medical_mae 权重不存在: {wp}\n'
        f'  主线先下载（见 README_pilot.md）：gdown 10wqOFCkhyWp6JdSFADrH6Xu9e1am3gXJ -O {wp}')

    model = timm.create_model(model_name, pretrained=False, num_classes=0)
    ckpt = torch.load(wp, map_location='cpu', weights_only=False)
    sd = ckpt.get('model', ckpt)
    # MAE pretrain ckpt 含 decoder + mask_token（解码器，特征抽取不用）-> 滤掉减少 unexpected 噪声
    sd = {k: v for k, v in sd.items()
          if not k.startswith('decoder') and k != 'mask_token'}
    msg = model.load_state_dict(sd, strict=False)
    logging.info(f'[medical_mae] load_state_dict Missing={msg.missing_keys} Unexpected={msg.unexpected_keys}')
    # 健全性：patch_embed/blocks 必须命中（只剩 head.* 类才算正常 missing）
    if any(k.startswith('patch_embed') or k.startswith('blocks') for k in msg.missing_keys):
        logging.warning('[medical_mae] ⚠️ patch_embed/blocks 出现 missing，键名可能不匹配，主线核 ckpt 结构')

    encoder = _freeze(_TimmViTTokens(model).to(device))
    num_tokens = (input_size // 16) ** 2  # 196
    meta = dict(name='medical_mae', paradigm='mae', source=wp, model=model_name,
                patch_size=16, input_size=input_size, pool='mean',
                missing_keys=list(msg.missing_keys), unexpected_keys=list(msg.unexpected_keys))
    # transform=None -> 用 datasets 默认 CXR 评测 transform（与 chexworld 同，CXR-pretrained 公平）
    return FrozenBackbone(encoder, feature_dim=768, num_tokens=num_tokens, meta=meta, transform=None)


# ===========================================================================
# rad_dino —— DINOv2 蒸馏 / ViT-B/14 / 518（HF microsoft/rad-dino，设计即 frozen 抽取器）
#   加载: AutoModel.from_pretrained('microsoft/rad-dino')（HF 自动缓存下载）
#   预处理: 用其官方 AutoImageProcessor（短边 518）—— 不硬编码常量，全照 processor
#   tokens: last_hidden_state[:,1:]（strip cls）  pool: pooler_output（CLS，按 researcher findings）
# ===========================================================================
class _HFRadDinoTokens(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        out = self.model(pixel_values=x)
        return out.last_hidden_state[:, 1:]           # strip cls -> patch tokens


class _HFRadDinoCls(nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        out = self.model(pixel_values=x)
        # rad-dino 官方示例用 pooler_output 作 CLS 嵌入；缺则退 last_hidden_state[:,0]
        return out.pooler_output if out.pooler_output is not None else out.last_hidden_state[:, 0]


class _HFProcessorTransform:
    """把 HF image processor 包成 torchvision 风格 transform：PIL -> tensor[3,H,W]（零硬编码常量）。"""
    def __init__(self, processor):
        self.processor = processor

    def __call__(self, img):
        out = self.processor(images=img, return_tensors='pt')
        return out['pixel_values'][0]


def _load_rad_dino(device, hf_id='microsoft/rad-dino'):
    from transformers import AutoModel, AutoImageProcessor  # 惰性 import
    model = AutoModel.from_pretrained(hf_id)
    processor = AutoImageProcessor.from_pretrained(hf_id)

    cfg = model.config
    patch_size = int(getattr(cfg, 'patch_size', 14))
    img_size = int(getattr(cfg, 'image_size', 518))
    feature_dim = int(getattr(cfg, 'hidden_size', 768))
    num_tokens = (img_size // patch_size) ** 2  # 518//14=37 -> 1369
    # ⚠️ 假设无 register token（RAD-DINO 基于无 register 的 DINOv2）；若 HF 版含 register，
    #    last_hidden_state[:,1:] 会多带 reg token、num_tokens 偏小 -> 主线烟测核 token 数后回填。
    tokens_mod = _freeze(_HFRadDinoTokens(model).to(device))
    cls_mod = _freeze(_HFRadDinoCls(model).to(device))  # 与 tokens_mod 共享同一 frozen model
    meta = dict(name='rad_dino', paradigm='dinov2-distill', source=hf_id, model='vit_base_patch14',
                patch_size=patch_size, input_size=img_size, pool='cls', feature_dim=feature_dim)
    return FrozenBackbone(tokens_mod, feature_dim=feature_dim, num_tokens=num_tokens, meta=meta,
                          transform=_HFProcessorTransform(processor), pooled_module=cls_mod)


# ===========================================================================
# radjepa —— I-JEPA / ViT-B/14 / 224（HF AIDElab-IITBombay/RadJEPA）
#   ⚠️未实测：arXiv 2601.15891 称公开，但 HF repo 可下性/输出格式未验证。
#   loader 写好但优雅降级：加载失败/包缺 -> NotImplementedError（run_pilot 归类 SKIP），主线 curl 验证后再启用。
#   TODO（主线/researcher 确认后回填）：
#     - JEPA encoder 输出格式（last_hidden_state？是否带 cls？token 数 256?）—— 烟测打印 shape 核对；
#     - 是否需 trust_remote_code / 自定义 build；预处理（224+norm？）。
# ===========================================================================
class _HFGenericTokens(nn.Module):
    """通用 HF encoder -> last_hidden_state（假设无 cls，JEPA 通常无）。待主线核 shape 后定 strip 与否。"""
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        out = self.model(pixel_values=x)
        return getattr(out, 'last_hidden_state', out[0] if isinstance(out, (tuple, list)) else out)


def _load_radjepa(device, hf_id='AIDElab-IITBombay/RadJEPA', input_size=224, patch_size=14):
    try:
        from transformers import AutoModel  # 惰性 import
    except Exception as e:
        raise NotImplementedError(f"radjepa: transformers 缺失或无法 import（{e}）；主线装环境后重试。")
    try:
        model = AutoModel.from_pretrained(hf_id, trust_remote_code=True)
    except Exception as e:
        raise NotImplementedError(
            f"radjepa: HF repo '{hf_id}' 加载失败（{e}）。\n"
            f"  ⚠️未实测可下性——主线先 curl 验证: "
            f"  python -c \"from huggingface_hub import snapshot_download; snapshot_download('{hf_id}')\"\n"
            f"  下不到则本 backbone 跳过；下到后核 encoder 输出格式（见 _load_radjepa TODO）再启用。")
    model = _freeze(model.to(device))
    encoder = _HFGenericTokens(model)
    num_tokens = (input_size // patch_size) ** 2  # 224//14=16 -> 256（待主线核实）
    meta = dict(name='radjepa', paradigm='i-jepa', source=hf_id, model='vit_base_patch14',
                patch_size=patch_size, input_size=input_size, pool='mean',
                note='⚠️未实测，token 格式/数 待主线烟测核对')
    # transform=None -> 暂用默认 CXR 评测 transform（224）；待主线确认 RadJEPA 官方预处理后回填
    return FrozenBackbone(encoder, feature_dim=768, num_tokens=num_tokens, meta=meta, transform=None)


# ===========================================================================
# imagenet_sup_vitb —— 监督(off-domain) / ViT-B/16 / 224（timm，作 off-domain 监督对照）
#   timm vit_base_patch16_224.augreg2_in21k_ft_in1k，pretrained=True，num_classes=0
#   预处理: timm 官方 data_config 的 eval transform（resize 256->crop 224，ImageNet norm）
#   pool: CLS（timm 监督 ViT 规范 global_pool='token'）
# ===========================================================================
def _load_imagenet_sup_vitb(device, model_name='vit_base_patch16_224.augreg2_in21k_ft_in1k',
                            input_size=224):
    import timm  # 惰性 import
    from timm.data import resolve_data_config, create_transform
    model = timm.create_model(model_name, pretrained=True, num_classes=0)
    cfg = resolve_data_config({}, model=model)
    transform = create_transform(**cfg, is_training=False)

    tokens_mod = _freeze(_TimmViTTokens(model).to(device))
    cls_mod = _freeze(_TimmViTCls(model).to(device))  # 共享同一 frozen model
    num_tokens = (input_size // 16) ** 2  # 196
    meta = dict(name='imagenet_sup_vitb', paradigm='supervised-offdomain', source=f'timm:{model_name}',
                model=model_name, patch_size=16, input_size=input_size, pool='cls',
                data_config=str(cfg))
    return FrozenBackbone(tokens_mod, feature_dim=768, num_tokens=num_tokens, meta=meta,
                          transform=transform, pooled_module=cls_mod)


# ===========================================================================
# chess —— 对比(MoCo 式) / ResNet50 / 224（备选低优先，mi2rl/CheSS）
#   官方 frozen 抽取: state_dict 去 'module.encoder_q.' 前缀 -> strict=False -> 冻结 -> avgpool 2048d
#   tokens: conv5 特征图 [B,2048,7,7] 展平成 [B,49,2048]  pool: mean(=global avgpool 2048)
#   ⚠️TODO: CheSS 官方 eval 归一化（mean/std）未在 findings 给出 -> 暂用 ImageNet+Grayscale(3) 标准做法，
#           researcher/主线核 mi2rl/CheSS repo 确认后回填（低优先，不阻塞 ViT 族主信号）。
# ===========================================================================
def _build_chess_transform(input_size=224, resize_size=256):
    from PIL import Image
    from torchvision import transforms
    from timm.data.constants import IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD
    return transforms.Compose([
        transforms.Resize(resize_size, interpolation=Image.BICUBIC),
        transforms.CenterCrop((input_size, input_size)),
        transforms.Grayscale(num_output_channels=3),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_DEFAULT_MEAN, std=IMAGENET_DEFAULT_STD),  # TODO 核 CheSS 专属 norm
    ])


def _load_chess(device, weights_path=None, input_size=224):
    import torchvision.models as tvm  # 惰性 import
    wp = weights_path or paths.CHESS_WEIGHTS
    assert os.path.exists(wp), (
        f'chess 权重不存在: {wp}\n'
        f'  主线先下载（见 README_pilot.md）：gdown 1IfiuQdKV7en9DFaB0NqNdsDkVbdyoVyD -O {wp}')

    resnet = tvm.resnet50(weights=None)
    ckpt = torch.load(wp, map_location='cpu', weights_only=False)
    sd = ckpt.get('state_dict', ckpt)
    # 官方: 取 query encoder，去 'module.encoder_q.' 前缀；丢弃 fc / projection head（strict=False）
    prefix = 'module.encoder_q.'
    enc_sd = {k[len(prefix):]: v for k, v in sd.items() if k.startswith(prefix)}
    if not enc_sd:  # 兼容无 module. 前缀的 ckpt
        prefix = 'encoder_q.'
        enc_sd = {k[len(prefix):]: v for k, v in sd.items() if k.startswith(prefix)}
    msg = resnet.load_state_dict(enc_sd, strict=False)
    logging.info(f'[chess] load_state_dict Missing={msg.missing_keys} Unexpected={msg.unexpected_keys}')
    if any(k.startswith('layer') or k.startswith('conv1') for k in msg.missing_keys):
        logging.warning('[chess] ⚠️ 主干层 missing，前缀可能不对，主线核 ckpt 键名')

    encoder = _freeze(_ResNetTokens(resnet).to(device))
    # ResNet50 @224 -> conv5 = 7x7 = 49 cell；pool=mean(over 49) 等价 global avgpool 2048d
    num_tokens = 49
    meta = dict(name='chess', paradigm='contrastive-moco', source=wp, model='resnet50',
                input_size=input_size, pool='mean', feature_dim=2048,
                missing_keys=list(msg.missing_keys), unexpected_keys=list(msg.unexpected_keys))
    return FrozenBackbone(encoder, feature_dim=2048, num_tokens=num_tokens, meta=meta,
                          transform=_build_chess_transform(input_size=input_size))


_LOADERS = {
    'chexworld': _load_chexworld,
    'medical_mae': _load_medical_mae,
    'rad_dino': _load_rad_dino,
    'radjepa': _load_radjepa,
    'imagenet_sup_vitb': _load_imagenet_sup_vitb,
    'chess': _load_chess,
}


def load_backbone(name, device='cuda', **kwargs):
    """统一入口。name in available_backbones()。"""
    if name not in _LOADERS:
        raise KeyError(f'未知 backbone {name}；可用: {list(_LOADERS)}')
    return _LOADERS[name](device=device, **kwargs)


def available_backbones():
    return list(_LOADERS)


if __name__ == '__main__':
    # 静态自检：只打印已注册 backbone，不加载权重、不前向（交主线烟测）
    print('registered backbones:', available_backbones())
    print('implemented(待主线烟测): chexworld(已验) | medical_mae | rad_dino | imagenet_sup_vitb | chess')
    print('⚠️未实测(优雅降级,主线 curl 验证): radjepa')
