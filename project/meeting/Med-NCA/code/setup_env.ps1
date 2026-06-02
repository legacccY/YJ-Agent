# Med-NCA Phase 0 environment setup (ASCII-only to avoid PS5.1 GBK decode bug)
# conda env mednca (py3.9) + torch cu118 + official requirements
$ErrorActionPreference = "Continue"
$root = "D:\YJ-Agent\project\meeting\Med-NCA"
$marker = "$root\code\setup_done.txt"
Remove-Item $marker -ErrorAction SilentlyContinue

Write-Host "=== [1/4] conda create mednca py3.9 ===" -ForegroundColor Cyan
conda create -n mednca python=3.9 -y

Write-Host "=== [2/4] torch cu118 (RTX 4070) ===" -ForegroundColor Cyan
conda run -n mednca pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

Write-Host "=== [3/4] official requirements ===" -ForegroundColor Cyan
conda run -n mednca pip install -r "$root\M3D-NCA-official\requirements.txt"

Write-Host "=== [4/4] verify torch.cuda ===" -ForegroundColor Cyan
$verify = conda run -n mednca python -c "import torch, torchio, nibabel; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOCUDA')"
Write-Host $verify -ForegroundColor Green

"DONE $(Get-Date -Format o)`n$verify" | Out-File -FilePath $marker -Encoding ascii
Write-Host "`n=== marker written: $marker ===" -ForegroundColor Yellow
Write-Host "Done. Window stays 60s then closes." -ForegroundColor Yellow
Start-Sleep -Seconds 60
