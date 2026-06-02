# Fix: requirements clobbered cu118 torch with CPU build. Force-reinstall cu118.
$ErrorActionPreference = "Continue"
$marker = "D:\YJ-Agent\project\meeting\Med-NCA\code\torch_done.txt"
Remove-Item $marker -ErrorAction SilentlyContinue

Write-Host "=== force-reinstall torch+torchvision cu118 ===" -ForegroundColor Cyan
conda run -n mednca pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu118

Write-Host "=== verify cuda + torchio import ===" -ForegroundColor Cyan
$v = conda run -n mednca python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOCUDA')); import torchio, nibabel, cv2; print('torchio', torchio.__version__, 'OK')"
Write-Host $v -ForegroundColor Green

"$v" | Out-File -FilePath $marker -Encoding ascii
Write-Host "=== marker written ===" -ForegroundColor Yellow
Start-Sleep -Seconds 30
