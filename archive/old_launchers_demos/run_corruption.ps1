Set-Location D:/YJ-Agent

Write-Host "[1/2] ResNet-50 starting..." -ForegroundColor Cyan
python project/scripts/test_corruption_robustness.py `
    --ckpt project/checkpoints/resnet50/best_resnet50.pth `
    --output-dir project/results/backbones/resnet50 `
    --split itb-lq `
    --qcts-params project/results/backbones/resnet50/qcts_params.json

$wsh = New-Object -ComObject Wscript.Shell
$wsh.Popup("ResNet-50 done! ViT-Tiny starting now.", 10, "Step 1/2 Done", 64) | Out-Null

Write-Host "[2/2] ViT-Tiny starting..." -ForegroundColor Cyan
python project/scripts/test_corruption_robustness.py `
    --ckpt project/checkpoints/vit_tiny/best_vit_tiny.pth `
    --output-dir project/results/backbones/vit_tiny `
    --split itb-lq `
    --qcts-params project/results/backbones/vit_tiny/qcts_params.json

$wsh.Popup("Both backbones done! 18 corruptions x Raw/TS/QCTS saved.", 15, "Experiment Complete", 64) | Out-Null
