# Med-NCA R2 data download: MSD Task05 Prostate (3D, ~230MB)
# Same S3 mirror as Task04. ASCII-only to avoid PS5.1 GBK decode bug.
$ErrorActionPreference = "Continue"
$data = "D:\YJ-Agent\project\meeting\Med-NCA\data"
$marker = "$data\task05_done.txt"
Remove-Item $marker -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $data | Out-Null

$tar = "$data\Task05_Prostate.tar"
$url = "https://msd-for-monai.s3-us-west-2.amazonaws.com/Task05_Prostate.tar"

if (Test-Path $tar) {
    Write-Host "exists, skip download: $tar" -ForegroundColor DarkGray
} else {
    Write-Host ">>> downloading $url" -ForegroundColor Cyan
    curl.exe -L --fail -o $tar $url
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!!! FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
        "FAILED exit $LASTEXITCODE $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding ascii
        Start-Sleep -Seconds 30
        exit 1
    }
    Write-Host "OK -> $tar" -ForegroundColor Green
}

Write-Host "=== extract Task05_Prostate ===" -ForegroundColor Yellow
# Windows 11 note: bundled tar (bsdtar) returns exit 1 on macOS ._* resource-fork
# warnings even when extraction succeeds. So DO NOT judge success by $LASTEXITCODE.
# Skip ._* at extract time, then verify by counting extracted .nii.gz files.
tar --exclude='._*' -xf $tar -C $data 2>$null

# Clean any ._* that slipped through
Get-ChildItem -Path "$data\Task05_Prostate" -Recurse -Filter "._*" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# Success = files actually present (NOT exit code)
$imgDir = "$data\Task05_Prostate\imagesTr"
if (-not (Test-Path $imgDir)) {
    Write-Host "!!! extract FAILED (no imagesTr dir)" -ForegroundColor Red
    "EXTRACT_FAILED $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding ascii
    Start-Sleep -Seconds 30
    exit 1
}

$nImg = (Get-ChildItem "$data\Task05_Prostate\imagesTr" -Filter "*.nii.gz" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "._*" }).Count
$nLbl = (Get-ChildItem "$data\Task05_Prostate\labelsTr" -Filter "*.nii.gz" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "._*" }).Count
Write-Host "imagesTr=$nImg  labelsTr=$nLbl" -ForegroundColor Green

"DONE img=$nImg lbl=$nLbl $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding ascii
Write-Host "`n=== Task05 done, marker: $marker ===" -ForegroundColor Yellow
Start-Sleep -Seconds 20
