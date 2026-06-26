#!/bin/bash
# =============================================================================
# setup_tscape_hpc.sh  —  QuantImmuBench §Tier-3  T-SCAPE HPC 一次性安装脚本
# 服务项目：quantimmu-bench §工具扩张v2 lever=部署T-SCAPE
#
# 运行位置：XJTLU HPC 登录节点（DTN: dtn.hpc.xjtlu.edu.cn）
#   !! 不要在 GPU 节点跑 !!（GPU 计费从 job 启动算，不能在 GPU 上下权重/clone）
#   !! 对外下载（clone + HF 权重）= 拍板点，主线串行执行 !!
#   用法：bash setup_tscape_hpc.sh
#
# 做的事：
#   1. git clone T-SCAPE repo 到 HPC 工作目录
#   2. patch dropout bug（src/model_fused.py 第 326 行）
#   3. conda 创建 tscape 环境（python=3.10 + pytorch cuda11.8 + 依赖）
#   4. 下载 HuggingFace 权重（~54.7GB，仅下 pmhc_im_neo 子目录）
#
# 预估耗时：
#   conda env 创建：~10-20 分钟
#   HF 权重下载（pmhc_im_neo 子目录，约 5-6GB 子集）：视 HPC 网速，~5-30 分钟
#   如果下全部 best_param/（54.7GB）：~30-120 分钟（TODO: 核实 HPC 带宽）
#
# 磁盘预留：
#   TODO: 核实所需磁盘 — best_param/ 全量 54.7GB + repo + env ~5GB
#         建议用 quota 命令确认 /gpfs/work/bio/jiayu2403/ 剩余空间 > 60GB
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
HPC_WORK=/gpfs/work/bio/jiayu2403/quantimmu
TSCAPE_DIR=${HPC_WORK}/t_scape
CONDA_BASE=/gpfs/work/bio/jiayu2403/.conda   # TODO: 核实 conda 安装路径（可能是 ~/miniconda3）
CONDA_ENV_NAME=tscape
PYTHON_BIN=${CONDA_BASE}/envs/${CONDA_ENV_NAME}/bin/python

# ---------------------------------------------------------------------------
# Step 0: 检查磁盘空间（警告，不阻断）
# ---------------------------------------------------------------------------
echo "=== [T-SCAPE setup] Step 0: 磁盘空间检查 ==="
echo "TODO: 下载 best_param/ 全量约 54.7GB，请确认剩余磁盘 > 60GB:"
df -h ${HPC_WORK} || true
# 如果需要仅下 pmhc_im_neo 子目录（推荐，节省空间），见 Step 4 注释

# ---------------------------------------------------------------------------
# Step 1: Clone T-SCAPE repo
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE setup] Step 1: Clone seoklab/T-SCAPE ==="
mkdir -p "${HPC_WORK}"

if [ -d "${TSCAPE_DIR}/.git" ]; then
    echo "[INFO] ${TSCAPE_DIR} 已存在，跳过 clone（如需重装先 rm -rf ${TSCAPE_DIR}）"
else
    echo "[INFO] clone T-SCAPE to ${TSCAPE_DIR} ..."
    git clone https://github.com/seoklab/T-SCAPE "${TSCAPE_DIR}"
    echo "[OK] clone 完成"
fi

# ---------------------------------------------------------------------------
# Step 2: Patch dropout bug（PR #3 未合并，必须手动 patch）
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE setup] Step 2: Patch dropout bug (src/model_fused.py:326) ==="
MODEL_FILE="${TSCAPE_DIR}/src/model_fused.py"

if [ ! -f "${MODEL_FILE}" ]; then
    echo "[ERROR] 找不到 ${MODEL_FILE}，请检查 clone 是否成功" >&2
    exit 1
fi

# 确认第 326 行内容（核实 patch 对准行）
echo "[INFO] 第 326 行原始内容："
sed -n '326p' "${MODEL_FILE}"

# patch：将 `F.dropout(e, self.dropout)` 改为 `F.dropout(e, self.dropout, training=self.training)`
# 仅替换精确字符串，不碰其他行
if grep -q 'F\.dropout(e, self\.dropout, training=self\.training)' "${MODEL_FILE}"; then
    echo "[INFO] patch 已存在，跳过（model_fused.py:326 已是正确版本）"
else
    # 安全替换（sed -i 原地修改，先备份）
    cp "${MODEL_FILE}" "${MODEL_FILE}.orig"
    sed -i 's/F\.dropout(e, self\.dropout)/F.dropout(e, self.dropout, training=self.training)/g' "${MODEL_FILE}"
    echo "[OK] dropout patch 施打完成"
    echo "[INFO] 备份保存为 ${MODEL_FILE}.orig"
    echo "[验证] 第 326 行 patch 后内容："
    sed -n '326p' "${MODEL_FILE}"
fi

# ---------------------------------------------------------------------------
# Step 2b: Patch pmhc_im_neo inference bug（官方发布代码缺陷，必须修才能跑 cancer 用例）
# ---------------------------------------------------------------------------
# 背景（D-tools3 窗 2026-06-26 实证 + researcher 核 GitHub）：
#   README 文档化 cancer 新抗原免疫原性用 `--inf_type pmhc_im_neo`，但发布代码：
#     ① load_state_dict 块只判 (pmhc_im | p_im) → pmhc_im_neo 权重根本没载入（停随机初始化）
#     ② 三个 task_dict 均无 "pmhc_im_neo" 键 → line 363 KeyError 直接崩
#   此 bug 从 initial commit 起 T-SCAPE + 前身 TITANiAN + 所有 fork 都有，无官方修法。
#   修法依据（非臆想，决定性验证）：
#     - ckpt 是 dict 含 keys ['epoch','model_state_dict']（torch.load 实测）→ 用 ckpt["model_state_dict"]
#     - state_dict key 为 shared_encoder... = Finaltask1_perf 架构（model_fused，顶层已 import）
#     - 该 state_dict 载入 Finaltask1_perf(d_model=300) **0 missing / 0 unexpected key**（实测干净匹配）
#     - 三个 task_dict 里 "pmhc_im"（免疫原性头）恒 = [3]，pmhc_im_neo 是其 cancer 变体 → 同头 [3]
#   ⚠️ T-SCAPE 结果须标注：用官方权重 + 修复官方 inference bug 跑（非原版代码，patch 依据如上）。
echo ""
echo "=== [T-SCAPE setup] Step 2b: Patch pmhc_im_neo inference bug ==="
INFER_FILE="${TSCAPE_DIR}/inference_csv.py"
"${PYTHON_BIN:-python}" - "$INFER_FILE" <<'PYEOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
oc = 'if (args.inf_type == "pmhc_im") | (args.inf_type == "p_im"):'
nc = 'if (args.inf_type == "pmhc_im") | (args.inf_type == "p_im") | (args.inf_type == "pmhc_im_neo") | (args.inf_type == "pmhc_im_inf"):'
ot = '{"pmhc_im":[3], "p_im":[1],'
nt = '{"pmhc_im":[3], "pmhc_im_neo":[3], "pmhc_im_inf":[3], "p_im":[1],'
if nc in s:
    print("[Step2b] inference patch 已存在，跳过")
else:
    assert s.count(oc) == 1, f"load-cond count={s.count(oc)}"
    assert s.count(ot) == 3, f"task_dict count={s.count(ot)}"
    s = s.replace(oc, nc).replace(ot, nt)
    p.write_text(s)
    print("[Step2b] inference patch OK：load 分支+1，task_dict+3")
PYEOF

# ---------------------------------------------------------------------------
# Step 3: 创建 conda 环境
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE setup] Step 3: 创建 conda 环境 ${CONDA_ENV_NAME} ==="

# TODO: 核实 conda 可执行路径（HPC 上可能需要 source ~/.bashrc 或 module load conda）
# 如果 conda 不在 PATH，取消下方注释并修改路径：
# source /gpfs/work/bio/jiayu2403/.conda/etc/profile.d/conda.sh

if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
    echo "[INFO] conda env ${CONDA_ENV_NAME} 已存在，跳过创建"
    echo "       如需重建：conda env remove -n ${CONDA_ENV_NAME}"
else
    echo "[INFO] 创建 conda env ${CONDA_ENV_NAME} (python=3.10)..."
    conda create -n ${CONDA_ENV_NAME} python=3.10 -y

    echo "[INFO] 安装 pytorch cuda11.8..."
    # TODO: 无官方 requirements.txt pin，版本坑风险已知（见 README.md §已知坑）
    # pytorch-cuda=11.8 对应 HPC gpu4090（Ampere 架构，CUDA ≥11.8 支持）
    conda install -n ${CONDA_ENV_NAME} \
        pytorch torchvision torchaudio pytorch-cuda=11.8 \
        -c pytorch -c nvidia -y

    echo "[INFO] 安装其他依赖..."
    # TODO: T-SCAPE 无 requirements.txt pin，以下为 README 列出依赖，版本以 conda/pip 默认为准
    conda install -n ${CONDA_ENV_NAME} \
        numpy matplotlib scikit-learn pandas wandb \
        -c conda-forge -y

    echo "[OK] conda env ${CONDA_ENV_NAME} 创建完成"
fi

echo "[INFO] 验证 python 路径："
echo "       ${PYTHON_BIN}"
ls -la "${PYTHON_BIN}" || echo "[WARN] python binary 路径需核实，检查 conda env list"

# ---------------------------------------------------------------------------
# Step 4: 下载 HuggingFace 权重
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE setup] Step 4: 下载 HuggingFace 权重 (seoklab/T-SCAPE) ==="
echo "[INFO] 权重目标目录：${TSCAPE_DIR}"
echo ""
echo "⚠️  权重约 54.7GB（全量 best_param/ 10 个 task），我们只用 pmhc_im_neo（cancer neoantigen）"
echo "⚠️  推荐：仅下载 pmhc_im_neo 子目录（约 5-6GB）节省磁盘"
echo ""
echo "TODO: 核实 HPC 上 huggingface-cli 是否可用，或改用 git lfs"
echo "      以下两种方式二选一："

# 方式 A（推荐）：用 huggingface-cli 只下 pmhc_im_neo 子目录
echo ""
echo "--- 方式 A：仅下载 pmhc_im_neo（推荐，节省磁盘）---"
echo "命令（确认无误后取消注释执行）："
echo ""
echo "  # 安装 huggingface_hub（若未安装）"
echo "  ${PYTHON_BIN} -m pip install huggingface_hub"
echo ""
echo "  # 只下 pmhc_im_neo 子目录（--include 过滤）"
echo "  ${PYTHON_BIN} -c \\"
echo "    \"from huggingface_hub import snapshot_download; \\"
echo "     snapshot_download('seoklab/T-SCAPE', local_dir='${TSCAPE_DIR}', \\"
echo "                       allow_patterns=['best_param/pmhc_im_neo/*'])\""
echo ""

# 方式 B：git lfs 全量（仅当需要其他任务时）
echo "--- 方式 B：git lfs 全量下载（54.7GB，非必要不推荐）---"
echo "命令："
echo "  cd ${TSCAPE_DIR} && git lfs pull"
echo ""

# 实际执行（取消下方注释以真正下载）：
# ---------- 取消注释以执行 ----------
# ${PYTHON_BIN} -m pip install huggingface_hub
# ${PYTHON_BIN} -c \
#   "from huggingface_hub import snapshot_download; \
#    snapshot_download('seoklab/T-SCAPE', local_dir='${TSCAPE_DIR}', \
#                      allow_patterns=['best_param/pmhc_im_neo/*'])"
# ---------- 取消注释结束 ----------

echo "[INFO] ⚠️  Step 4 权重下载命令已打印但未执行（对外下载=拍板点，主线确认后取消注释）"
echo "[INFO] 下载完成后验证："
echo "       ls -lh ${TSCAPE_DIR}/best_param/pmhc_im_neo/"

# ---------------------------------------------------------------------------
# 完成
# ---------------------------------------------------------------------------
echo ""
echo "=== [T-SCAPE setup] 安装完成摘要 ==="
echo "  repo     : ${TSCAPE_DIR}"
echo "  env      : ${CONDA_ENV_NAME}"
echo "  python   : ${PYTHON_BIN}"
echo "  dropout patch: 已施打（src/model_fused.py:326）"
echo ""
echo "下一步："
echo "  1. 取消 Step 4 注释，执行权重下载（或手动跑方式 A/B 命令）"
echo "  2. 权重就位后，提交 submit_tscape.sbatch 跑推理"
echo "  3. 参考 README.md 完整步骤"
