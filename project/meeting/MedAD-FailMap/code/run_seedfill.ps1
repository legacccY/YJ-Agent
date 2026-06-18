# =============================================================================
# run_seedfill.ps1 — MedAD-FailMap Phase 2 seed-fill (续跑/幂等)
#
# 目标: 补齐 vae seed1/seed2 + memae seed1/seed2 共 4 个 run,
#       使 vae/memae 各拥有 3 seeds (42/1/2), 凑 PR-5 confirmatory 方差带。
#
# 运行方式 (主线 Start-Process 跑, 勿直接调):
#   Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File D:\YJ-Agent\project\meeting\MedAD-FailMap\code\run_seedfill.ps1' -NoNewWindow -Wait
#
# 预计时间: ~2h (单卡 RTX4070, 每个 run ~30min x 4 = ~2h)
# 硬件: -g 0 (单卡), 串行 (不挤正在跑的)
# 完整命令链 (每个 run 均复刻 s42 产物结构):
#   1. train_recon_ae.py  -> train_log + ckpt + anomaly_scores + config
#   2. stratify_eval.py   -> stratify_{size,contrast,interact,per_image}_<model>.csv
#   3. stratify_significance.py (x3: P85/P90/P95)
#                         -> stratify_significance_FA_<model>_P85/P90/P95.csv
#   4. conspicuity_proxy.py (tumor only)
#                         -> conspicuity_features_tumor_<model>.csv
#   5. incremental_stats.py
#                         -> incremental_C2/C3/C4_x5/FC_family csvs
#
# 幂等规则:
#   - train_log 达到 250 行 (250 epochs) + anomaly_scores csv 存在 => skip
#   - 否则清掉 out-dir 重跑 (半截如 vae_s1 会被清掉)
#
# 不启动训练: 此脚本由主线 Start-Process 跑, Coder 只交脚本
# =============================================================================

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUNBUFFERED = "1"

# ---- 路径常量 ---------------------------------------------------------------
$REPO    = "D:\YJ-Agent\project\meeting\MedAD-FailMap"
$CODE    = "$REPO\code"
$DATA    = "$REPO\data"
$RES     = "$REPO\results"
$PHASE2  = "$REPO\results\phase2"

# conspicuity normal csv (Phase 0 产物, C4 共用)
$NORMAL_CONSPICUITY = "$RES\conspicuity_features_normal.csv"

# ---- 待填 run 列表 ----------------------------------------------------------
# 格式: @(model, seed)
$RUNS = @(
    @("vae",   1),
    @("vae",   2),
    @("memae", 1),
    @("memae", 2)
)

# ---- 工具函数 ----------------------------------------------------------------

function Test-RunComplete {
    param($outDir, $model)
    $logCsv = "$outDir\train_log_brats_${model}.csv"
    $scoreCsv = "$outDir\anomaly_scores_brats_${model}.csv"
    if (-not (Test-Path $logCsv) -or -not (Test-Path $scoreCsv)) { return $false }
    # 计行数 (含 header = 251 行 => 250 epochs)
    $lines = (Get-Content $logCsv | Measure-Object -Line).Lines
    return ($lines -ge 251)
}

function Invoke-Step {
    param([string]$label, [string]$cmd)
    Write-Host ""
    Write-Host ">>> $label" -ForegroundColor Cyan
    Write-Host "    $cmd"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "STEP FAILED [$label] exit=$LASTEXITCODE"
    }
}

# ---- 主循环 -----------------------------------------------------------------

foreach ($run in $RUNS) {
    $MODEL = $run[0]
    $SEED  = $run[1]
    $TAG   = "${MODEL}_s${SEED}"
    $OUTDIR = "$PHASE2\$TAG"
    $LOGFILE = "$PHASE2\${TAG}.log"

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  RUN: $TAG  (model=$MODEL seed=$SEED)"  -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow

    # ---- 幂等检查 ----
    if (Test-RunComplete -outDir $OUTDIR -model $MODEL) {
        Write-Host "[SKIP] $TAG already complete (train_log 250 epochs + anomaly_scores found)" -ForegroundColor Green
        continue
    }

    # ---- 半截目录清除 ----
    if (Test-Path $OUTDIR) {
        Write-Host "[CLEAN] removing incomplete $OUTDIR ..." -ForegroundColor Magenta
        Remove-Item -Recurse -Force $OUTDIR
    }
    New-Item -ItemType Directory -Force -Path $OUTDIR | Out-Null

    # ---- 开始 tee 到日志 (PowerShell 无原生 tee, 用 Start-Transcript) ----
    Start-Transcript -Path $LOGFILE -Append

    try {

        # ==== STEP 1: 训练 ====
        Invoke-Step "1-train $TAG" `
            "python `"$CODE\train_recon_ae.py`" -d brats -m $MODEL --seed $SEED --out-dir `"$OUTDIR`" -g 0 --data-root `"$DATA`""

        # ==== STEP 2: stratify_eval ====
        Invoke-Step "2-stratify_eval $TAG" `
            ("python `"$CODE\stratify_eval.py`"" +
             " --score-csv `"$OUTDIR\anomaly_scores_brats_${MODEL}.csv`"" +
             " --mask-dir `"$DATA\BraTS2021\test\annotation`"" +
             " --tumor-img-dir `"$DATA\BraTS2021\test\tumor`"" +
             " --out-dir `"$OUTDIR`"" +
             " --model-tag $MODEL")

        # ==== STEP 3: stratify_significance (三档敏感性扫描) ====
        foreach ($pct in @(85, 90, 95)) {
            Invoke-Step "3-stratify_sig P${pct} $TAG" `
                ("python `"$CODE\stratify_significance.py`"" +
                 " --score-csv `"$OUTDIR\anomaly_scores_brats_${MODEL}.csv`"" +
                 " --strat-per-image-csv `"$OUTDIR\stratify_per_image_${MODEL}.csv`"" +
                 " --out-csv `"$OUTDIR\stratify_significance_FA_${MODEL}_P${pct}.csv`"" +
                 " --threshold-pct $pct")
        }

        # ==== STEP 4: conspicuity_proxy (tumor only) ====
        Invoke-Step "4-conspicuity $TAG" `
            ("python `"$CODE\conspicuity_proxy.py`"" +
             " --img-dir `"$DATA\BraTS2021\test\tumor`"" +
             " --score-csv `"$OUTDIR\anomaly_scores_brats_${MODEL}.csv`"" +
             " --out-csv `"$OUTDIR\conspicuity_features_tumor_${MODEL}.csv`"")

        # ==== STEP 5: incremental_stats (C2/C3/C4/FC) ====
        Invoke-Step "5-incremental_stats $TAG" `
            ("python `"$CODE\incremental_stats.py`"" +
             " --conspicuity-csv `"$OUTDIR\conspicuity_features_tumor_${MODEL}.csv`"" +
             " --stratify-csv `"$OUTDIR\stratify_interact_${MODEL}.csv`"" +
             " --normal-conspicuity-csv `"$NORMAL_CONSPICUITY`"" +
             " --score-csv `"$OUTDIR\anomaly_scores_brats_${MODEL}.csv`"" +
             " --out-dir `"$OUTDIR`"")

        Write-Host ""
        Write-Host "[DONE] $TAG complete." -ForegroundColor Green

    } catch {
        Write-Host "[ERROR] $TAG failed: $_" -ForegroundColor Red
        Stop-Transcript
        throw
    }

    Stop-Transcript
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ALL SEED-FILL RUNS COMPLETE"               -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
