# Resume ISIC 2018 Task1 input zip (11.16GB) with retry loop, ASCII-only
$ErrorActionPreference = "Continue"
$data = "D:\YJ-Agent\project\meeting\Med-NCA\data"
$url  = "https://isic-challenge-data.s3.amazonaws.com/2018/ISIC2018_Task1-2_Training_Input.zip"
$out  = "$data\ISIC2018_Task1-2_Training_Input.zip"
$marker = "$data\isic_done.txt"
$target = 11165358566
Remove-Item $marker -ErrorAction SilentlyContinue

for ($i = 1; $i -le 30; $i++) {
    $sz = (Get-Item $out -ErrorAction SilentlyContinue).Length
    if (-not $sz) { $sz = 0 }
    Write-Host "=== attempt $i : local $sz / $target ===" -ForegroundColor Cyan
    if ($sz -ge $target) { Write-Host "COMPLETE" -ForegroundColor Green; break }
    # -C - resume, retry transient errors
    curl.exe -L -C - --retry 10 --retry-delay 5 --retry-all-errors -o $out $url
    Start-Sleep -Seconds 3
}

$final = (Get-Item $out -ErrorAction SilentlyContinue).Length
if ($final -ge $target) {
    "DONE $final $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding ascii
    Write-Host "=== ISIC input COMPLETE $final ===" -ForegroundColor Yellow
} else {
    "PARTIAL $final $(Get-Date -Format o)" | Out-File -FilePath $marker -Encoding ascii
    Write-Host "=== still partial $final / $target after 30 tries ===" -ForegroundColor Red
}
Write-Host "Window stays 60s." -ForegroundColor Yellow
Start-Sleep -Seconds 60
