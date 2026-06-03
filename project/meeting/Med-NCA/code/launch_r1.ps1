$env:R1_EPOCHS = "1000"
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
$env:PYTHONUNBUFFERED = "1"
$log = "D:\YJ-Agent\project\meeting\Med-NCA\results\r1_train.log"
& "D:\Anaconda\envs\mednca\python.exe" -u "D:\YJ-Agent\project\meeting\Med-NCA\code\run_r1_hippocampus.py" *>&1 | Tee-Object -FilePath $log
Write-Host "=== R1 EXITED ==="
