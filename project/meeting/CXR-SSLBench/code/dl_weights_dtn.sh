#!/bin/bash
# DTN(有外网) 下 SSL 权重。HF 优先(快)，MAE gdown 最后(Google Drive 慢，best-effort)。
ENV=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310
W=/gpfs/work/bio/jiayu2403/cxr-sslbench/cache/weights
cd $W
echo "[$(date)] START dl (HF-first)"
rm -f $W/.hf_done $W/.dl_done

echo "[1] timm imagenet vitb"
$ENV/bin/python -c "import timm; m=timm.create_model('vit_base_patch16_224.augreg2_in21k_ft_in1k', pretrained=True, num_classes=0); print('[timm] OK', sum(p.numel() for p in m.parameters()))" 2>&1 | tail -2

echo "[2] HF rad-dino"
$ENV/bin/python -c "from huggingface_hub import snapshot_download; print('[raddino]', snapshot_download('microsoft/rad-dino'))" 2>&1 | tail -2

echo "[3] HF RadJEPA (试)"
$ENV/bin/python -c "from huggingface_hub import snapshot_download; print('[radjepa]', snapshot_download('AIDElab-IITBombay/RadJEPA'))" 2>&1 | tail -3

echo "[$(date)] HF done"
touch $W/.hf_done

echo "[4] gdown medical_mae 1.34G (Google Drive 慢, best-effort)"
$ENV/bin/python -c "import gdown; gdown.download(id='10wqOFCkhyWp6JdSFADrH6Xu9e1am3gXJ', output='medical_mae_vitb.pth', quiet=True)" 2>&1 | tail -2
$ENV/bin/python -c "import torch; ck=torch.load('$W/medical_mae_vitb.pth',map_location='cpu',weights_only=False); k=ck.get('model',ck); print('[mae] OK keys=',len(k))" 2>&1 | tail -1

echo "[$(date)] DONE dl"
touch $W/.dl_done
