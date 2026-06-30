#!/bin/bash
# =============================================================================
# CXR-SSLBench Phase1 块A 预训练提交脚本（HPC gpu4090，薄包装官方 SSL repo）
# 用法（主线经 gpu_slot 调度后提交；本脚本只准备 + 跑，不自己 sbatch）：
#   sbatch submit_pretrain.sh <method> <seed> <mode> <gpus>
#     method = mae|dino|moco|chexworld
#     mode   = smoke|full
#     gpus   = 参与训练卡数（默认 1；DINO/MoCo 无 accum，eff_bs 靠 gpus×batch 凑官方值）
# ⚠️ R4：超参全在 pretrain/recipe_<method>.py 冻结，本脚本不另填超参，只拼预算/路径/clone。
# =============================================================================
#SBATCH --job-name=cxrssl_pt
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --account=shuihuawang
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=30:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/cxr-sslbench/logs/pt_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/cxr-sslbench/logs/pt_%j.err
# ⚠️ --gres=gpu:N 与下面 GPUS 须由主线提交时按需改（sbatch 头不吃 shell 变量）。

set -e
METHOD="${1:?method=mae|dino|moco|chexworld}"
SEED="${2:-0}"
MODE="${3:-full}"          # smoke|full
GPUS="${4:-1}"

# ---- 路径（真源 paths.py；HPC 绝对路径在此对齐）----
ROOT=/gpfs/work/bio/jiayu2403/cxr-sslbench
CODE=$ROOT/code
VENDOR=$ROOT/vendor          # 官方 repo clone 落处
DATA=/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/images-224/images-224  # TODO 主线核实子路径(paths.py 同)
RESULTS=$ROOT/results
ENV=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310
PY=$ENV/bin/python
mkdir -p $ROOT/logs $VENDOR $RESULTS/pretrain
cd $CODE

export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=8
echo "[$(date)] method=$METHOD seed=$SEED mode=$MODE gpus=$GPUS node=$(hostname)"
$PY -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.device_count())"

# ---- clone 官方 repo（compute 节点无外网 → 须 DTN/login 节点预 clone；此处幂等检查）----
clone_repo () {  # $1=dir $2=giturl
  if [ ! -d "$VENDOR/$1" ]; then
    echo "[clone] $1 <- $2 （⚠️ compute 节点无外网，须在 login/DTN 节点先 git clone 到 $VENDOR/$1）"
    git clone "$2" "$VENDOR/$1" || { echo "clone 失败：请主线在 DTN 预 clone"; exit 2; }
  fi
}
case "$METHOD" in
  mae)   clone_repo mae   https://github.com/facebookresearch/mae.git;       REPO=$VENDOR/mae ;;
  dino)  clone_repo dino  https://github.com/facebookresearch/dino.git;      REPO=$VENDOR/dino ;;
  moco)  clone_repo moco  https://github.com/facebookresearch/moco-v3.git;   REPO=$VENDOR/moco ;;
  chexworld) REPO=/gpfs/work/bio/jiayu2403/chexworld/repo ;;   # 本地官方 repo，不 clone
  *) echo "未知 method $METHOD"; exit 1 ;;
esac

# ---- 预算：mode→E_eq（smoke 用 reduced epoch 数，=矩阵 §2）----
if [ "$MODE" = "smoke" ]; then
  case "$METHOD" in
    dino) E_EQ=10 ;;   # SMK-DINO 10 eff-ep
    moco) E_EQ=15 ;;   # SMK-MOCO 15 eff-ep
    *)    E_EQ=5  ;;    # MAE/CheX 廉价 loss-sanity 烟测（矩阵 §2 skeptic-3）
  esac
else
  E_EQ=100           # 全预算 images-seen=11.21M
fi

# ---- eff_bs 凑官方值：batch_size_per_gpu / accum_iter（主线按 4090 24GB 显存 + 烟测 imgs/sec 标定调）----
# ⚠️ TODO 主线：以下 BPG/ACCUM 是占位默认，须用 smoke 标定的单卡可容 batch 回填（OOM 则降 BPG 升 ACCUM）。
case "$METHOD" in
  mae)       OFF_EFF=4096; BPG=256; ACCUM=$(( OFF_EFF / (BPG*GPUS) )) ;;     # 4096=256×accum×gpus
  dino)      OFF_EFF=512;  ACCUM=1; BPG=$(( OFF_EFF / GPUS )) ;;             # DINO 无 accum，512=BPG×gpus
  moco)      OFF_EFF=4096; ACCUM=1; BPG=$(( OFF_EFF / GPUS )) ;;             # MoCo 无 accum；4090×4 装不下 4096→见 TODO-B reduced 路径
  chexworld) OFF_EFF=2048; BPG=128; ACCUM=$(( OFF_EFF / (BPG*GPUS) )) ;;     # 2048=128×accum×gpus
esac
echo "[budget] E_eq=$E_EQ off_eff_bs=$OFF_EFF BPG=$BPG ACCUM=$ACCUM GPUS=$GPUS"

OUT=$ROOT/runs/${METHOD}_s${SEED}_${MODE}
mkdir -p $OUT

# ---- 拼官方训练命令（recipe print-cmd，超参全在 recipe 内冻结）----
CMD=$($PY pretrain/recipe_${METHOD}.py --mode print-cmd \
        --seed $SEED --e_eq $E_EQ --world_size $GPUS \
        --batch_size_per_gpu $BPG --accum_iter $ACCUM \
        --repo_dir $REPO --data_path $DATA --output_dir $OUT --results_dir $RESULTS)
echo "[train-cmd] $CMD"

# ---- 跑训练（moco-v3 写 cwd → 须在 $OUT 下跑）----
RUN=${METHOD}_s${SEED}_${MODE}
( cd $OUT && PYTHONPATH=$REPO $PY -c "pass" )   # 占位，确保 $OUT 可写
echo "[$(date)] === TRAIN START run=$RUN ==="
# ⚠️ TODO-MONITOR-HOOK：DINO teacher 熵/特征 std 需在官方 loop 调 smoke_monitor.MonitorWriter.log_step 灌入。
#    官方 main_dino 不 emit → 须主线在 vendor/dino/main_dino.py 训练 loop 末插 ~5 行 monitor hook（监控非算法改）。
#    未挂 hook 时 gate 走 --tail 只拿 loss → DINO/MoCo collapse 判据返回 INCOMPLETE（不放行假 PASS）。
( cd $OUT && PYTHONPATH=$REPO eval "$CMD" ) 2>&1 | tee $OUT/train.log
echo "[$(date)] === TRAIN DONE ==="

# ---- 烟测 gate：投全量前强制（矩阵 §2）----
if [ "$MODE" = "smoke" ]; then
  SGC=""; [ "$METHOD" = "moco" ] && SGC="--stop_grad_conv1 true"
  BATCHARG=""; [ "$METHOD" = "moco" ] && BATCHARG="--batch $OFF_EFF"
  echo "[$(date)] === SMOKE GATE ==="
  # 优先读 monitor 写的 smoke_<method>.csv（含熵/std）；缺则 --tail 解析 train.log（只 loss → 可能 INCOMPLETE）
  if [ -f "$RESULTS/smoke_${METHOD}.csv" ]; then
    $PY smoke_monitor.py --mode verdict --method $METHOD --csv $RESULTS/smoke_${METHOD}.csv \
        --results_dir $RESULTS --run $RUN --seed $SEED $BATCHARG $SGC || GATE_FAIL=1
  else
    $PY smoke_monitor.py --mode tail-verdict --method $METHOD --log $OUT/train.log \
        --results_dir $RESULTS --run $RUN --seed $SEED $BATCHARG $SGC || GATE_FAIL=1
  fi
  if [ "${GATE_FAIL:-0}" = "1" ]; then
    echo "[GATE] $METHOD 非 PASS → 停，报主线拍板（矩阵 §2 失败动作：官方缓解→重烟测；仍塌→公开权重标 mismatch）"
    exit 3
  fi
  echo "[GATE] $METHOD PASS → 解锁全量"
  exit 0
fi

# ---- 全量：export 中间 ckpt 到统一 schema（25/50/100 eff-ep）----
echo "[$(date)] === EXPORT INTERMEDIATE CKPTS ==="
# ⚠️ TODO 主线：各官方 repo 原生 ckpt 文件命名/epoch 落盘点需在 HPC 实测核对后填 SRC 路径：
#   dino: $OUT/checkpoint{EPOCH:04d}.pth（saveckp_freq=25 → 0024/0049/0099 或 25/50/100，核实命名）
#   mae:  $OUT/checkpoint-{EPOCH}.pth（原生 20-cadence → 实际落 20/40/60/80/99，export 按实际 ep 记 meta）
#   moco: $OUT/checkpoint_{EPOCH:04d}.pth.tar（核实是否每 epoch 落盘）
#   chexworld: $OUT/<exp_name>/seed${SEED}/epoch_{24,49,99}.pth.tar（eval_list 已设）
for EP in 25 50 100; do
  IDX=$(( EP - 1 ))
  case "$METHOD" in
    dino)      SRC=$OUT/checkpoint$(printf '%04d' $EP).pth ;;       # TODO 核命名(可能 0-based)
    mae)       SRC=$OUT/checkpoint-$IDX.pth ;;                       # TODO 20-cadence 取最近，按实际命名
    moco)      SRC=$OUT/checkpoint_$(printf '%04d' $IDX).pth.tar ;;  # TODO 核命名
    chexworld) SRC=$OUT/aprime_nih_e100/seed${SEED}/epoch_${IDX}.pth.tar ;;
  esac
  if [ -f "$SRC" ]; then
    EXTRA=""; [ "$METHOD" = "moco" ] && EXTRA="--total_batch $OFF_EFF"
    $PY pretrain/recipe_${METHOD}.py --mode export --src_ckpt "$SRC" --ep $EP \
        --seed $SEED --results_dir $RESULTS $EXTRA
    echo "[export] ep$EP <- $SRC"
  else
    echo "[export][WARN] ep$EP 源 ckpt 不存在: $SRC（主线核 repo 落盘命名/cadence）"
  fi
done
echo "[$(date)] === ALL DONE → block B 消费 $RESULTS/pretrain/${METHOD}_s${SEED}_ep*.pth ==="
