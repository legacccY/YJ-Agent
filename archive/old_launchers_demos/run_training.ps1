Set-Location D:/YJ-Agent
$wsh = New-Object -ComObject Wscript.Shell

# ── ConvNeXt-Tiny ──────────────────────────────────────────────────────────────
Write-Host "[1/6] ConvNeXt-Tiny training..." -ForegroundColor Cyan
python project/train_vit_tiny.py --config project/configs/convnext_tiny.yaml
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("ConvNeXt-Tiny training FAILED. Check window for error.", 30, "ERROR", 16) | Out-Null
    exit 1
}

Write-Host "[2/6] ConvNeXt-Tiny infer_backbone..." -ForegroundColor Cyan
python project/infer_backbone.py `
    --ckpt project/checkpoints/convnext_tiny/best_vit_tiny.pth `
    --output-dir project/results/backbones/convnext_tiny
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("ConvNeXt-Tiny infer FAILED.", 30, "ERROR", 16) | Out-Null
    exit 1
}

Write-Host "[3/6] ConvNeXt-Tiny QCTS fit + eval..." -ForegroundColor Cyan
python project/run_qcts_backbone.py `
    --backbone-dir project/results/backbones/convnext_tiny `
    --backbone-name "ConvNeXt-Tiny" `
    --exclude-diverse
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("ConvNeXt-Tiny QCTS FAILED.", 30, "ERROR", 16) | Out-Null
    exit 1
}

$wsh.Popup("ConvNeXt-Tiny done (train+infer+QCTS). Starting Swin-Tiny now.", 15, "Step 1/2 Done", 64) | Out-Null

# ── Swin-Tiny ──────────────────────────────────────────────────────────────────
Write-Host "[4/6] Swin-Tiny training..." -ForegroundColor Cyan
python project/train_vit_tiny.py --config project/configs/swin_tiny.yaml
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("Swin-Tiny training FAILED. Check window for error.", 30, "ERROR", 16) | Out-Null
    exit 1
}

Write-Host "[5/6] Swin-Tiny infer_backbone..." -ForegroundColor Cyan
python project/infer_backbone.py `
    --ckpt project/checkpoints/swin_tiny/best_vit_tiny.pth `
    --output-dir project/results/backbones/swin_tiny
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("Swin-Tiny infer FAILED.", 30, "ERROR", 16) | Out-Null
    exit 1
}

Write-Host "[6/6] Swin-Tiny QCTS fit + eval..." -ForegroundColor Cyan
python project/run_qcts_backbone.py `
    --backbone-dir project/results/backbones/swin_tiny `
    --backbone-name "Swin-Tiny" `
    --exclude-diverse
if ($LASTEXITCODE -ne 0) {
    $wsh.Popup("Swin-Tiny QCTS FAILED.", 30, "ERROR", 16) | Out-Null
    exit 1
}

$wsh.Popup("All done! ConvNeXt-Tiny + Swin-Tiny trained, inferred, QCTS fitted. Check section54_summary.csv.", 20, "Training Complete", 64) | Out-Null
Write-Host "All 6 steps complete." -ForegroundColor Green
