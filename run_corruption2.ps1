Set-Location D:/YJ-Agent
$wsh = New-Object -ComObject Wscript.Shell

Write-Host "[1/2] ResNet-50 corruption rerun (with rho)..." -ForegroundColor Cyan
python project/scripts/test_corruption_robustness.py `
    --ckpt project/checkpoints/resnet50/best_resnet50.pth `
    --output-dir project/results/backbones/resnet50 `
    --split itb-lq `
    --qcts-params project/results/backbones/resnet50/qcts_params.json
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("ResNet-50 corruption FAILED.", 30, "ERROR", 16) | Out-Null; exit 1
}

Write-Host "[2/2] ViT-Tiny corruption rerun (with rho)..." -ForegroundColor Cyan
python project/scripts/test_corruption_robustness.py `
    --ckpt project/checkpoints/vit_tiny/best_vit_tiny.pth `
    --output-dir project/results/backbones/vit_tiny `
    --split itb-lq `
    --qcts-params project/results/backbones/vit_tiny/qcts_params.json
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("ViT-Tiny corruption FAILED.", 30, "ERROR", 16) | Out-Null; exit 1
}

$wsh.Popup("Corruption rerun done. CSV now has raw_rho/ts_rho/qcts_rho per corruption.", 15, "Done", 64) | Out-Null
Write-Host "All corruption reruns complete." -ForegroundColor Green
