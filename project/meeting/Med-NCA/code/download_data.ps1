# Med-NCA Phase 0 data download (R1 Hippocampus + R2 ISIC 2018)
# All public S3 direct links, ASCII-only to avoid PS5.1 GBK decode bug
$ErrorActionPreference = "Continue"
$data = "D:\YJ-Agent\project\meeting\Med-NCA\data"
$marker = "$data\download_done.txt"
Remove-Item $marker -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $data | Out-Null

function Get-File($url, $out) {
    if (Test-Path $out) { Write-Host "exists, skip: $out" -ForegroundColor DarkGray; return }
    Write-Host ">>> downloading $url" -ForegroundColor Cyan
    curl.exe -L --fail -o $out $url
    if ($LASTEXITCODE -ne 0) { Write-Host "!!! FAILED $url (exit $LASTEXITCODE)" -ForegroundColor Red }
    else { Write-Host "OK -> $out" -ForegroundColor Green }
}

Write-Host "=== [1/3] MSD Task04 Hippocampus (3D, R1) ===" -ForegroundColor Yellow
Get-File "https://msd-for-monai.s3-us-west-2.amazonaws.com/Task04_Hippocampus.tar" "$data\Task04_Hippocampus.tar"

Write-Host "=== [2/3] ISIC 2018 Task1 input images (2D, R2, ~10GB slow) ===" -ForegroundColor Yellow
Get-File "https://isic-challenge-data.s3.amazonaws.com/2018/ISIC2018_Task1-2_Training_Input.zip" "$data\ISIC2018_Task1-2_Training_Input.zip"

Write-Host "=== [3/3] ISIC 2018 Task1 GT mask ===" -ForegroundColor Yellow
Get-File "https://isic-challenge-data.s3.amazonaws.com/2018/ISIC2018_Task1_Training_GroundTruth.zip" "$data\ISIC2018_Task1_Training_GroundTruth.zip"

Write-Host "=== extract Hippocampus ===" -ForegroundColor Yellow
if (Test-Path "$data\Task04_Hippocampus.tar") {
    tar -xf "$data\Task04_Hippocampus.tar" -C $data
    Write-Host "Hippocampus extracted" -ForegroundColor Green
}

"DONE $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding ascii
Write-Host "`n=== all downloads done, marker: $marker ===" -ForegroundColor Yellow
Write-Host "Window stays 60s." -ForegroundColor Yellow
Start-Sleep -Seconds 60
