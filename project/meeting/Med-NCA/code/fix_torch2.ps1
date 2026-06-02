# Fix2: pin exact cu118 wheel + no-cache to defeat CPU fallback / cached cpu wheel
$ErrorActionPreference = "Continue"
$marker = "D:\YJ-Agent\project\meeting\Med-NCA\code\torch2_done.txt"
Remove-Item $marker -ErrorAction SilentlyContinue

Write-Host "=== uninstall existing torch/torchvision ===" -ForegroundColor Cyan
conda run -n mednca pip uninstall -y torch torchvision

Write-Host "=== install pinned torch 2.4.1+cu118 (no cache) ===" -ForegroundColor Cyan
conda run -n mednca pip install --no-cache-dir torch==2.4.1+cu118 torchvision==0.19.1+cu118 --index-url https://download.pytorch.org/whl/cu118

Write-Host "=== verify ===" -ForegroundColor Cyan
$v = conda run -n mednca python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOCUDA'))"
Write-Host $v -ForegroundColor Green

"$v" | Out-File -FilePath $marker -Encoding ascii
Write-Host "=== marker written ===" -ForegroundColor Yellow
Start-Sleep -Seconds 30
