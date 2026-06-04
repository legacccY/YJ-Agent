$env:R1_EPOCHS = "3"
$env:R1_MODEL_TAG = "r1_bench"
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
$env:PYTHONUNBUFFERED = "1"
$log = "D:\YJ-Agent\project\meeting\Med-NCA\results\_r1_bench.log"
$t0 = Get-Date
& "D:\Anaconda\envs\mednca\python.exe" -u "D:\YJ-Agent\project\meeting\Med-NCA\code\run_r1_hippocampus.py" *>&1 | Tee-Object -FilePath $log
$dt = (Get-Date) - $t0
"WALL_TOTAL_SEC=$([int]$dt.TotalSeconds)" | Tee-Object -FilePath $log -Append
