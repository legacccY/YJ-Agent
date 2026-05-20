Set-Location D:/YJ-Agent
$wsh = New-Object -ComObject Wscript.Shell

Write-Host "[1/3] Swin-Tiny training..." -ForegroundColor Cyan
python project/train_vit_tiny.py --config project/configs/swin_tiny.yaml
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("Swin-Tiny training FAILED.", 30, "ERROR", 16) | Out-Null; exit 1
}

Write-Host "[2/3] Swin-Tiny infer_backbone..." -ForegroundColor Cyan
python project/infer_backbone.py `
    --ckpt project/checkpoints/swin_tiny/best_vit_tiny.pth `
    --output-dir project/results/backbones/swin_tiny
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("Swin-Tiny infer FAILED.", 30, "ERROR", 16) | Out-Null; exit 1
}

Write-Host "[3/3] Swin-Tiny QCTS fit + eval..." -ForegroundColor Cyan
python project/run_qcts_backbone.py `
    --backbone-dir project/results/backbones/swin_tiny `
    --backbone-name "Swin-Tiny" `
    --exclude-diverse
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("Swin-Tiny QCTS FAILED.", 30, "ERROR", 16) | Out-Null; exit 1
}

$wsh.Popup("Swin-Tiny done! Train+Infer+QCTS complete.", 15, "Swin Done", 64) | Out-Null
Write-Host "SWIN_PIPELINE_DONE" -ForegroundColor Green
