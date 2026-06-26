#!/bin/bash
# HyperFidBench HyperGALE env — 离线装（从 dtn 预下 wheelhouse；torch2.0.1+cu118 + PyG2.3.1 官方 pin）
# 修订：step4 改 --no-deps 分组装 + 显式补 runtime deps，避免离线 pip 回溯地狱
# step0 改幂等（venv 存在就复用，不删已装好的 torch/PyG）
set -e
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
WH=$ROOT/wheelhouse
BASEPY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
mkdir -p $ROOT/logs

echo "=== 0. wheelhouse 清单（供比对，共 N wheel）==="
ls $WH | sort
echo "--- wheelhouse 共 $(ls $WH | wc -l) 个文件 ---"

echo "=== 0b. venv 幂等（存在就复用，不删已装的 torch/PyG）==="
if [ ! -d "$ROOT/hf_hypergale_venv" ]; then
    echo "  建新 venv..."
    $BASEPY -m venv $ROOT/hf_hypergale_venv
else
    echo "  venv 已存在，复用（跳建 venv）"
fi
PY=$ROOT/hf_hypergale_venv/bin/python

OFF="--no-index --find-links $WH --disable-pip-version-check"

echo "=== 1. 基础工具（pip/setuptools 先升，离线）==="
# setuptools-82.0.1 在 wheelhouse 里已确认
$PY -m pip install $OFF --no-deps setuptools 2>&1 | tail -3
$PY -m pip install $OFF --no-deps wheel 2>&1 | tail -3 || true

echo "=== 2. torch 2.0.1+cu118 + torchvision（--no-deps 跳 triton）==="
# 检查是否已装，已装跳过
$PY -c "import torch; v=torch.__version__; assert '2.0.1' in v, v" 2>/dev/null && echo "  torch 2.0.1 已装，跳过" || {
    $PY -m pip install $OFF --no-deps torch==2.0.1+cu118 2>&1 | tail -3
    $PY -m pip install $OFF --no-deps torchvision==0.15.2+cu118 2>&1 | tail -3
    # torch runtime deps（--no-deps 下手动补）
    # 从 wheelhouse 确认存在：filelock, sympy, mpmath, networkx, jinja2, MarkupSafe, fsspec,
    # typing-extensions, numpy, pillow（torchvision 需要）
    # numpy 必须 pin <2：torch2.0.1+cu118 编译于 numpy1.x，wheelhouse 默认最高 2.2.6 会崩
    # (braingb venv 装 1.26.4 没炸；hg 无 pin 装 2.2.6 → "compiled using NumPy 1.x cannot run in 2.2.6")
    $PY -m pip install $OFF --no-deps filelock sympy mpmath jinja2 MarkupSafe \
        typing-extensions numpy==1.26.4 pillow 2>&1 | tail -3
    # fsspec 已在 wheelhouse（lightning 也需要）
    $PY -m pip install $OFF --no-deps fsspec 2>&1 | tail -3
}

echo "=== 3. PyG 生态（离线，官方 pin）==="
$PY -c "import torch_geometric; v=torch_geometric.__version__; assert '2.3' in v, v" 2>/dev/null && echo "  PyG 2.3.x 已装，跳过" || {
    $PY -m pip install $OFF --no-deps torch_geometric==2.3.1 2>&1 | tail -3
    $PY -m pip install $OFF --no-deps torch_scatter==2.1.1 torch_sparse==0.6.17 torch_cluster==1.6.1 2>&1 | tail -3
}

echo "=== 4a. 公共 runtime deps（多个框架包共享）==="
# packaging: lightning/torchmetrics/hydra/wandb 全依赖
# PyYAML: hydra/omegaconf/wandb 全依赖
# tqdm: wandb/nilearn/gensim 全依赖
# requests: wandb/nilearn/ogb 全依赖（连带 certifi/charset-normalizer/idna/urllib3）
# six: wandb/GitPython 依赖
$PY -m pip install $OFF --no-deps packaging PyYAML tqdm 2>&1 | tail -3
$PY -m pip install $OFF --no-deps certifi charset-normalizer idna urllib3 requests 2>&1 | tail -3
$PY -m pip install $OFF --no-deps six python-dateutil pytz tzdata 2>&1 | tail -3

echo "=== 4b. lightning_utilities（torchmetrics + pytorch_lightning 共同 dep）==="
# lightning_utilities-0.15.3: deps = packaging, typing-extensions（已装）
# NOTE: wheelhouse 里文件名是 lightning_utilities-0.15.3-py3-none-any.whl
# 但 PyPI 包名也叫 lightning-utilities（破折号），两种名字 pip 都认
$PY -m pip install $OFF --no-deps lightning_utilities==0.15.3 2>&1 | tail -3 || \
$PY -m pip install $OFF --no-deps lightning-utilities==0.15.3 2>&1 | tail -3

echo "=== 4c. torchmetrics==1.1.0（--no-deps + 手补 deps）==="
# torchmetrics runtime deps: torch(已装), numpy(已装), packaging(已装), lightning_utilities(已装)
$PY -m pip install $OFF --no-deps torchmetrics==1.1.0 2>&1 | tail -3

echo "=== 4d. pytorch_lightning==2.0.7（--no-deps + 手补 deps）==="
# pytorch_lightning runtime deps:
#   torch(已装), torchmetrics(已装), lightning_utilities(已装),
#   packaging(已装), PyYAML(已装), fsspec(已装), tqdm(已装),
#   typing-extensions(已装), numpy(已装)
# 可选 dep wandb 不在这里装（4f 单独装）
$PY -m pip install $OFF --no-deps pytorch-lightning==2.0.7 2>&1 | tail -3 || \
$PY -m pip install $OFF --no-deps pytorch_lightning==2.0.7 2>&1 | tail -3

echo "=== 4e. omegaconf==2.3.0 + hydra-core==1.3.2（--no-deps + 手补 deps）==="
# omegaconf runtime deps: antlr4-python3-runtime==4.9.3, PyYAML(已装)
# 从 wheelhouse 确认: antlr4-python3-runtime-4.9.3 在 wheelhouse（hydra 下载时带的）
$PY -m pip install $OFF --no-deps antlr4-python3-runtime==4.9.3 2>&1 | tail -3
$PY -m pip install $OFF --no-deps omegaconf==2.3.0 2>&1 | tail -3
# hydra-core runtime deps: omegaconf(已装), antlr4-python3-runtime(已装), packaging(已装)
$PY -m pip install $OFF --no-deps hydra-core==1.3.2 2>&1 | tail -3

echo "=== 4f. wandb==0.15.0（--no-deps + 手补 deps）==="
# wandb runtime deps:
#   Click, GitPython, requests(已装), psutil, sentry-sdk, six(已装),
#   docker-pycreds, pathtools, setproctitle, PyYAML(已装), protobuf,
#   appdirs（老版 wandb 需要）
# 从 requirements.txt 确认存在：
#   Click-8.1.3, GitPython-3.1.31, gitdb-4.0.10, smmap-5.0.0（GitPython 链），
#   psutil, sentry-sdk-1.21.0, docker-pycreds-0.4.0, pathtools-0.1.2,
#   setproctitle-1.3.2, protobuf-3.20.3, appdirs-1.4.4
$PY -m pip install $OFF --no-deps click 2>&1 | tail -3
$PY -m pip install $OFF --no-deps smmap gitdb GitPython 2>&1 | tail -3
$PY -m pip install $OFF --no-deps psutil sentry-sdk docker-pycreds pathtools setproctitle 2>&1 | tail -3
$PY -m pip install $OFF --no-deps protobuf appdirs 2>&1 | tail -3
$PY -m pip install $OFF --no-deps wandb==0.15.0 2>&1 | tail -3

echo "=== 4g. dhg==0.9.3（--no-deps + 手补 deps）==="
# dhg runtime deps（从 PyPI metadata + requirements.txt）:
#   torch(已装), numpy(已装), scipy, matplotlib, scikit-learn,
#   pandas(装，Step4k), tqdm(已装)
# scipy 需要: numpy(已装)
# matplotlib 需要: numpy(已装), pillow(已装), contourpy, cycler, fonttools,
#   kiwisolver, packaging(已装), pyparsing, python-dateutil(已装)
# scikit-learn 需要: numpy(已装), scipy, joblib, threadpoolctl
$PY -m pip install $OFF --no-deps scipy 2>&1 | tail -3
$PY -m pip install $OFF --no-deps contourpy cycler fonttools kiwisolver pyparsing 2>&1 | tail -3
$PY -m pip install $OFF --no-deps matplotlib 2>&1 | tail -3
$PY -m pip install $OFF --no-deps joblib threadpoolctl 2>&1 | tail -3
# 去版本 pin：wheelhouse 是 pip download 下的最新版（scikit_learn-1.7.2），论文 pin 1.2.2 离线找不到
$PY -m pip install $OFF --no-deps scikit-learn 2>&1 | tail -3
$PY -m pip install $OFF --no-deps dhg==0.9.3 2>&1 | tail -3

echo "=== 4h. nilearn==0.10.1 + nibabel==5.1.0（--no-deps + 手补 deps）==="
# nilearn runtime deps: numpy(已装), scipy(已装), scikit-learn(已装), joblib(已装),
#   matplotlib(已装), nibabel, pandas, requests(已装), tqdm(已装), lxml
# nibabel runtime deps: numpy(已装), packaging(已装)
$PY -m pip install $OFF --no-deps lxml 2>&1 | tail -3
$PY -m pip install $OFF --no-deps nibabel 2>&1 | tail -3 || true
# 去 pandas pin（wheelhouse 是 pandas-2.3.3）；dhg 需要 pandas
$PY -m pip install $OFF --no-deps pandas 2>&1 | tail -3
# nilearn：cc200 路线 FC 现成不自建，nilearn 非必需，装失败不阻断
$PY -m pip install $OFF --no-deps nilearn 2>&1 | tail -3 || echo "  nilearn 跳过（cc200 路线不需要）"

echo "=== 4i. deepsnap（--no-deps，从 wheelhouse .zip）==="
# deepsnap deps: torch(已装), torch_geometric(已装), networkx(已装), numpy(已装)
# wheelhouse 里是 deepsnap-0.2.1.zip（任务描述确认）
$PY -m pip install $OFF --no-deps deepsnap 2>&1 | tail -2 || echo "  deepsnap 离线装失败（可忽略，HyperGALE 仅 import 不用运行时超图 ops）"

echo "=== 4j. 其余 HyperGALE 需要的包 ==="
# networkx: torch_geometric 和 deepsnap 都依赖；torch 也用
$PY -m pip install $OFF --no-deps networkx 2>&1 | tail -3
# numba: HyperGALE requirements 里有；依赖 llvmlite, numpy(已装)
$PY -m pip install $OFF --no-deps llvmlite 2>&1 | tail -3
$PY -m pip install $OFF --no-deps numba==0.57.1 2>&1 | tail -3 || echo "  numba 装失败（非核心依赖，继续）"
# optuna: 依赖 cmaes, alembic(SQLAlchemy), colorlog, packaging(已装), tqdm(已装)
$PY -m pip install $OFF --no-deps SQLAlchemy Mako greenlet 2>&1 | tail -3
$PY -m pip install $OFF --no-deps alembic cmaes colorlog 2>&1 | tail -3
$PY -m pip install $OFF --no-deps optuna==3.2.0 2>&1 | tail -3 || echo "  optuna 装失败（非核心依赖，继续）"
# ogb: 依赖 torch(已装), scikit-learn(已装), pandas(已装), tqdm(已装), outdated
$PY -m pip install $OFF --no-deps outdated littleutils 2>&1 | tail -3
$PY -m pip install $OFF --no-deps ogb==1.3.6 2>&1 | tail -3 || echo "  ogb 装失败（非核心依赖，继续）"
# gensim: 依赖 numpy(已装), scipy(已装), smart-open
$PY -m pip install $OFF --no-deps smart-open 2>&1 | tail -3
$PY -m pip install $OFF --no-deps gensim==4.3.1 2>&1 | tail -3 || echo "  gensim 装失败（非核心依赖，继续）"
# ipdb（调试用）
$PY -m pip install $OFF --no-deps ipdb 2>&1 | tail -3 || true

echo "=== 5. 验 import（核心依赖）==="
$PY -c "import torch; print('torch', torch.__version__, 'cuda', torch.version.cuda)"
$PY -c "import torch_sparse, torch_scatter, torch_cluster; print('pyg-ext', torch_sparse.__version__)"
$PY -c "import torch_geometric as g; print('pyg', g.__version__)"
$PY -c "import pytorch_lightning as pl; print('pytorch_lightning', pl.__version__)"
$PY -c "import torchmetrics; print('torchmetrics', torchmetrics.__version__)"
$PY -c "import hydra, omegaconf; print('hydra OK, omegaconf', omegaconf.__version__)"
$PY -c "import wandb; print('wandb', wandb.__version__)"
$PY -c "import dhg; print('dhg', dhg.__version__)"
$PY -c "import nilearn; print('nilearn', nilearn.__version__)" 2>/dev/null || echo "  nilearn 未装（cc200 路线不需要，OK）"
$PY -c "import nibabel; print('nibabel', nibabel.__version__)" 2>/dev/null || echo "  nibabel 未装（cc200 路线不需要，OK）"
$PY -c "import deepsnap; print('deepsnap OK')" 2>/dev/null || echo "  deepsnap import 失败（可忽略）"
echo "=== HYPERGALE ENV DONE ==="
