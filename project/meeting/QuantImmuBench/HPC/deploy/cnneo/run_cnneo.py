"""
run_cnneo.py — QuantImmuBench §扩张v2  CNNeo/CNNeoPP 推理脚本
服务项目：quantimmu-bench §工具扩张v2 lever=部署CNNeo apples-to-apples

功能：
  从 CNNeoPP 三个 notebook 抽出推理逻辑，统一为可批量运行的 Python 脚本。
  支持两种子模型：

  --model fcnn_tf（默认）：
    TF-IDF + 全连接网络（FCNN），CPU 友好，无需外部模型下载。
    对应 repo/models/CNNeo_FCN_TF.ipynb 的逻辑。
    输入：peptide + HLA（标准 HLA-A*02:01 格式），内部去 * 处理。
    编码：6-mer k-mers + TF-IDF(max_features=1000)。

  --model cnn_biobert：
    BioBERT 嵌入 + TextCNN（旗舰模型，需 transformers + HuggingFace 下载）。
    对应 repo/models/CNNeo_CNN_BioBERT.ipynb 的逻辑。
    编码：4-mer k-mers → BioBERT(dmis-lab/biobert-base-cased-v1.1) 嵌入 → TextCNN。
    推理较慢，推荐 GPU，HPC 可用。

重要说明：
  - repo 不含预训练权重，首次运行自动从 training_data.xlsx 训练并保存权重。
  - 权重默认保存在 HPC/deploy/cnneo/weights/（--weights-dir 可覆盖）。
  - 训练数据：repo/training_data/training_data.xlsx（列：Mutated Peptide, HLA type, label）。
  - FCNN_BioBERT 子模型需要 BA/TAP 等额外特征列，当前输入不支持，已排除。
  - 输出 score：class=1（免疫原）的 softmax 概率，0-1 越高越免疫原。

用法：
  # 全量（FCNN_TF，首次自动训练）
  python run_cnneo.py

  # 烟测（首次训练完成后只推理 10 对）
  python run_cnneo.py --smoke 10

  # CNN_BioBERT 子模型（需 transformers 已安装）
  python run_cnneo.py --model cnn_biobert

  # 指定路径
  python run_cnneo.py \\
      --input-csv scripts/out/newtools/cnneo_input.csv \\
      --output-csv scripts/out/newtools/cnneo_raw_output.csv \\
      --weights-dir HPC/deploy/cnneo/weights \\
      --training-data HPC/deploy/cnneo/repo/training_data/training_data.xlsx

Windows 规范：
  - DataLoader num_workers=0（spawn 多进程在 Windows 有问题，0 = 主进程内完成）
  - pin_memory=False
  - 路径用 pathlib.Path，不用反斜杠
"""

from __future__ import annotations

import argparse
import pathlib
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# 常量（镜像 notebook 超参，零改动）
# ---------------------------------------------------------------------------

FCNN_TF_HIDDEN_SIZE   = 64
FCNN_TF_OUTPUT_SIZE   = 2
FCNN_TF_DROPOUT       = 0.2
FCNN_TF_EPOCHS        = 45
FCNN_TF_LR            = 0.0001
FCNN_TF_BATCH_SIZE    = 32
FCNN_TF_MAX_FEATURES  = 1000    # TF-IDF max_features
FCNN_TF_KMER_SIZE     = 6

CNN_BB_NUM_FILTERS    = 120
CNN_BB_FILTER_SIZES   = [3, 4, 5]
CNN_BB_OUTPUT_SIZE    = 2
CNN_BB_DROPOUT        = 0.2
CNN_BB_EPOCHS         = 19
CNN_BB_LR             = 0.0001
CNN_BB_BATCH_SIZE     = 32
CNN_BB_KMER_SIZE      = 4
CNN_BB_MAX_LEN        = 64      # BioBERT tokenizer max_length
CNN_BB_MODEL_NAME     = "dmis-lab/biobert-base-cased-v1.1"

PAD_CHAR              = "X"
PAD_TARGET_LEN        = 11      # trans_Mutated 目标长度（超过不截断）
RANDOM_SEED           = 42
SMOTE_SEED            = 1


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------

def hla_strip_star(hla: str) -> str:
    """
    HLA-A*02:01 → HLA-A02:01（去除 *，去除首尾空格及不间断空格）。
    镜像 notebook cell-1 的三行 str.replace。
    """
    hla = hla.strip()
    hla = hla.replace("*", "")
    hla = hla.replace(" ", "")
    hla = hla.replace("\xa0", "")
    return hla


def pad_peptide(seq: str, target: int = PAD_TARGET_LEN) -> str:
    """
    补 X 到 target 长度；超过 target 不截断（镜像 trans_Mutated）。
    """
    diff = target - len(seq)
    if diff > 0:
        seq = seq + PAD_CHAR * diff
    return seq


def get_kmers_text(hla_stripped: str, padded_pep: str, k: int) -> str:
    """
    连接 stripped_HLA + padded_peptide，切 k-mer，全小写，空格分隔。
    镜像 notebook getKmers()。
    """
    seq = hla_stripped + padded_pep
    kmers = [seq[i : i + k].lower() for i in range(len(seq) - k + 1)]
    return " ".join(kmers)


def build_kmer_texts(df: pd.DataFrame, k: int) -> list[str]:
    """
    对 df 的 peptide / hla 列生成 k-mer 文本列表。
    df 必须含 'peptide'（原始序列）和 'hla'（标准 HLA-A*02:01 格式）。
    """
    texts = []
    for _, row in df.iterrows():
        hla_s  = hla_strip_star(str(row["hla"]))
        padded = pad_peptide(str(row["peptide"]))
        texts.append(get_kmers_text(hla_s, padded, k))
    return texts


# ---------------------------------------------------------------------------
# 公共数据集类
# ---------------------------------------------------------------------------

class TensorDataset(Dataset):
    def __init__(self, X: torch.Tensor, y: torch.Tensor) -> None:
        self.X = X
        self.y = y

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, idx: int):
        return self.X[idx], self.y[idx]


class InferenceDataset(Dataset):
    """仅 X，无标签（推理阶段）。"""

    def __init__(self, X: torch.Tensor) -> None:
        self.X = X

    def __len__(self) -> int:
        return len(self.X)

    def __getitem__(self, idx: int):
        return self.X[idx]


# ============================================================================
# FCNN_TF 子模型
# ============================================================================

class FCNNModel(nn.Module):
    """
    镜像 CNNeo_FCN_TF.ipynb 的 FullyConnectedModel。
    input_size = TF-IDF max_features（默认 1000）
    hidden_size = 64, output_size = 2
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = FCNN_TF_HIDDEN_SIZE,
        output_size: int = FCNN_TF_OUTPUT_SIZE,
    ) -> None:
        super().__init__()
        self.fc1  = nn.Linear(input_size, hidden_size)
        self.relu = nn.ReLU()
        self.fc2  = nn.Linear(hidden_size, output_size)
        self.drop = nn.Dropout(p=FCNN_TF_DROPOUT)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.fc1(x)
        x = self.relu(x)
        x = self.drop(x)
        x = self.fc2(x)
        return x


def train_fcnn_tf(
    training_data_path: pathlib.Path,
    weights_dir: pathlib.Path,
) -> None:
    """
    用 training_data.xlsx 训练 FCNN_TF 并保存权重。
    镜像 CNNeo_FCN_TF.ipynb 全流程，保持超参零改动。

    产出（weights_dir 下）：
      fcnn_tf_vectorizer.pkl — 训练好的 TF-IDF 向量化器
      fcnn_tf_model.pth      — 训练好的 FCNN 权重
    """
    try:
        from imblearn.over_sampling import SMOTE
    except ImportError as e:
        print(
            "[run_cnneo][FCNN_TF] 训练需要 imbalanced-learn：pip install imbalanced-learn",
            file=sys.stderr,
        )
        raise e

    print("[run_cnneo][FCNN_TF] 开始训练……", file=sys.stderr)
    print(f"[run_cnneo][FCNN_TF] 训练数据: {training_data_path}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 读训练数据
    # ------------------------------------------------------------------
    if not training_data_path.exists():
        print(
            f"[run_cnneo] ERROR: training_data 不存在: {training_data_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    data = pd.read_excel(training_data_path)
    print(f"[run_cnneo][FCNN_TF] 读入训练数据 {len(data)} 行，列: {list(data.columns)[:10]}",
          file=sys.stderr)

    # 检查必要列
    required_cols = {"Mutated Peptide", "HLA type", "label"}
    missing = required_cols - set(data.columns)
    if missing:
        print(
            f"[run_cnneo] ERROR: training_data.xlsx 缺少必要列: {missing}\n"
            f"  实际列（前 15）: {list(data.columns)[:15]}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 镜像 notebook cell-1：去 * 及空格
    data["HLA type"] = data["HLA type"].astype(str).str.replace("*", "", regex=False)
    data["HLA type"] = data["HLA type"].str.replace(" ", "", regex=False)
    data["HLA type"] = data["HLA type"].str.replace("\xa0", "", regex=False)

    # 镜像 trans_Mutated
    data["M"] = data["Mutated Peptide"].astype(str).apply(pad_peptide)

    y = data["label"].astype(int)

    # ------------------------------------------------------------------
    # 生成 6-mer 文本，拟合 TF-IDF
    # ------------------------------------------------------------------
    def _get_kmers_text_row(row: pd.Series) -> str:
        seq = str(row["HLA type"]) + str(row["M"])
        kmers = [seq[i : i + FCNN_TF_KMER_SIZE].lower()
                 for i in range(len(seq) - FCNN_TF_KMER_SIZE + 1)]
        return " ".join(kmers)

    data["trans"] = data.apply(_get_kmers_text_row, axis=1)

    vectorizer = TfidfVectorizer(
        max_features=FCNN_TF_MAX_FEATURES,
        smooth_idf=True,
        use_idf=True,
    )
    x_scale = vectorizer.fit_transform(data["trans"]).toarray()
    print(
        f"[run_cnneo][FCNN_TF] TF-IDF 矩阵 shape: {x_scale.shape}",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------
    # 切分数据集（镜像 notebook：seed=42）
    # ------------------------------------------------------------------
    torch.manual_seed(RANDOM_SEED)

    X = torch.tensor(x_scale, dtype=torch.float32)
    y_tensor = torch.tensor(y.values, dtype=torch.long)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_tensor, test_size=0.2, random_state=RANDOM_SEED, stratify=y_tensor
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, random_state=RANDOM_SEED, stratify=y_train
    )

    # SMOTE 过采样（训练集，镜像 notebook）
    smote = SMOTE(random_state=SMOTE_SEED)
    x_train_res, y_train_res = smote.fit_resample(X_train.numpy(), y_train.numpy())
    x_train_res = torch.tensor(x_train_res, dtype=torch.float32)
    y_train_res = torch.tensor(y_train_res, dtype=torch.long)

    train_ds = TensorDataset(x_train_res, y_train_res)
    val_ds   = TensorDataset(X_val, y_val)

    # Windows: num_workers=0, pin_memory=False
    train_loader = DataLoader(
        train_ds,
        batch_size=FCNN_TF_BATCH_SIZE,
        shuffle=True,
        num_workers=0,
        pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=FCNN_TF_BATCH_SIZE,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    # ------------------------------------------------------------------
    # 训练 FCNN（镜像 notebook：epochs=45, lr=0.0001）
    # ------------------------------------------------------------------
    device    = torch.device("cpu")   # CPU 训练
    input_sz  = x_scale.shape[1]      # 1000
    model     = FCNNModel(input_sz).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=FCNN_TF_LR)

    print(
        f"[run_cnneo][FCNN_TF] FCNN 结构: input={input_sz}, hidden={FCNN_TF_HIDDEN_SIZE}, "
        f"output={FCNN_TF_OUTPUT_SIZE}, epochs={FCNN_TF_EPOCHS}",
        file=sys.stderr,
    )

    for epoch in range(FCNN_TF_EPOCHS):
        model.train()
        total_loss    = 0.0
        total_correct = 0
        total_samples = 0

        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = model(inputs)
            loss = criterion(outputs, targets)

            _, predicted = torch.max(outputs, 1)
            total_samples += targets.size(0)
            total_correct += (predicted == targets).sum().item()
            total_loss    += loss.item() * inputs.size(0)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        avg_loss = total_loss / len(train_loader.dataset)
        acc      = 100.0 * total_correct / total_samples

        # 验证集
        model.eval()
        val_correct = 0
        val_samples = 0
        with torch.no_grad():
            for inputs, targets in val_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                outputs = model(inputs)
                _, predicted = torch.max(outputs, 1)
                val_samples += targets.size(0)
                val_correct += (predicted == targets).sum().item()
        val_acc = 100.0 * val_correct / val_samples

        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(
                f"[FCNN_TF] Epoch [{epoch+1}/{FCNN_TF_EPOCHS}] "
                f"Loss={avg_loss:.4f}, TrainAcc={acc:.2f}%, ValAcc={val_acc:.2f}%",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # 保存权重和向量化器
    # ------------------------------------------------------------------
    weights_dir.mkdir(parents=True, exist_ok=True)
    model_path      = weights_dir / "fcnn_tf_model.pth"
    vectorizer_path = weights_dir / "fcnn_tf_vectorizer.pkl"

    torch.save(model.state_dict(), model_path)
    with open(vectorizer_path, "wb") as f:
        pickle.dump(vectorizer, f)

    print(f"[run_cnneo][FCNN_TF] 权重已保存: {model_path}", file=sys.stderr)
    print(f"[run_cnneo][FCNN_TF] 向量化器已保存: {vectorizer_path}", file=sys.stderr)
    print("[run_cnneo][FCNN_TF] 训练完成。", file=sys.stderr)


def run_inference_fcnn_tf(
    input_csv: pathlib.Path,
    output_csv: pathlib.Path,
    model_path: pathlib.Path,
    vectorizer_path: pathlib.Path,
    smoke: int = 0,
    batch_size: int = 512,
) -> None:
    """
    FCNN_TF 推理：读 cnneo_input.csv → 输出 cnneo_raw_output.csv。
    score = softmax 概率（class=1，越高越免疫原）。
    """
    # ------------------------------------------------------------------
    # 加载向量化器和模型
    # ------------------------------------------------------------------
    print(f"[run_cnneo][FCNN_TF] 加载向量化器: {vectorizer_path}", file=sys.stderr)
    with open(vectorizer_path, "rb") as f:
        vectorizer: TfidfVectorizer = pickle.load(f)

    input_sz = len(vectorizer.vocabulary_)
    print(
        f"[run_cnneo][FCNN_TF] TF-IDF vocab size={input_sz}",
        file=sys.stderr,
    )

    model = FCNNModel(input_sz)
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    print(f"[run_cnneo][FCNN_TF] 模型已加载: {model_path}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 读输入 CSV
    # ------------------------------------------------------------------
    if not input_csv.exists():
        print(
            f"[run_cnneo] ERROR: 输入文件不存在: {input_csv}",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_csv(input_csv, dtype=str)
    df["peptide"] = df["peptide"].str.strip()
    df["hla"]     = df["hla"].str.strip()

    if smoke > 0:
        print(
            f"[run_cnneo][FCNN_TF] --smoke {smoke}：只推理前 {smoke} 行",
            file=sys.stderr,
        )
        df = df.head(smoke)

    n_total = len(df)
    print(f"[run_cnneo][FCNN_TF] 待推理 {n_total} 个 (peptide, hla) 对", file=sys.stderr)

    # ------------------------------------------------------------------
    # 预处理：生成 6-mer 文本 → TF-IDF transform
    # ------------------------------------------------------------------
    trans_texts = build_kmer_texts(df, k=FCNN_TF_KMER_SIZE)
    # transform（非 fit_transform），使用训练时的词表
    x_infer = vectorizer.transform(trans_texts).toarray()
    X_tensor = torch.tensor(x_infer, dtype=torch.float32)

    infer_ds     = InferenceDataset(X_tensor)
    infer_loader = DataLoader(
        infer_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    # ------------------------------------------------------------------
    # 推理
    # ------------------------------------------------------------------
    all_scores = []
    device = torch.device("cpu")

    with torch.no_grad():
        for batch_X in infer_loader:
            batch_X = batch_X.to(device)
            logits  = model(batch_X)
            probs   = F.softmax(logits, dim=1)
            scores  = probs[:, 1].cpu().numpy()
            all_scores.append(scores)

    scores_arr = np.concatenate(all_scores)
    labels_arr = (scores_arr > 0.5).astype(int)

    # ------------------------------------------------------------------
    # 写输出
    # ------------------------------------------------------------------
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result_df = df[["peptide", "hla"]].copy()
    result_df["score"] = scores_arr
    result_df["label"] = labels_arr

    result_df.to_csv(output_csv, index=False, encoding="utf-8")

    n_pos = int(labels_arr.sum())
    print(f"[run_cnneo][FCNN_TF] 推理完成，共 {n_total} 对", file=sys.stderr)
    print(f"[run_cnneo][FCNN_TF] 预测免疫原（label=1, score>0.5）: {n_pos}", file=sys.stderr)
    print(
        f"[run_cnneo][FCNN_TF] score 统计: "
        f"min={scores_arr.min():.4f}, max={scores_arr.max():.4f}, "
        f"mean={scores_arr.mean():.4f}",
        file=sys.stderr,
    )
    print(f"[run_cnneo][FCNN_TF] 输出: {output_csv}", file=sys.stderr)


# ============================================================================
# CNN_BioBERT 子模型（可选，需 transformers）
# ============================================================================

class TextCNN(nn.Module):
    """
    镜像 CNNeo_CNN_BioBERT.ipynb 的 TextCNN。
    input_size=768（BioBERT hidden dim），num_filters=120，filter_sizes=[3,4,5]，output=2。
    """

    def __init__(
        self,
        input_size: int,
        num_filters: int = CNN_BB_NUM_FILTERS,
        filter_sizes: list[int] = CNN_BB_FILTER_SIZES,
        output_size: int = CNN_BB_OUTPUT_SIZE,
        dropout: float = CNN_BB_DROPOUT,
    ) -> None:
        super().__init__()
        self.convs = nn.ModuleList([
            nn.Conv2d(1, num_filters, (fs, input_size)) for fs in filter_sizes
        ])
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(num_filters * len(filter_sizes), output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [batch, seq_len, 768]
        x = x.unsqueeze(1)                                       # [batch, 1, seq_len, 768]
        x = [F.relu(conv(x)).squeeze(3) for conv in self.convs]  # [[batch, num_filters, L], ...]
        x = [F.max_pool1d(c, c.size(2)).squeeze(2) for c in x]   # [[batch, num_filters], ...]
        x = torch.cat(x, dim=1)                                   # [batch, num_filters*3]
        x = self.dropout(x)
        return self.fc(x)


def _embed_biobert(
    texts: list[str],
    tokenizer,
    biobert_model,
    max_length: int = CNN_BB_MAX_LEN,
    batch_size: int = 32,
    device: torch.device = torch.device("cpu"),
) -> torch.Tensor:
    """
    批量 BioBERT 嵌入，返回 [N, max_length, 768]。
    分批处理避免 OOM。
    """
    all_feats = []
    biobert_model.eval()

    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start : start + batch_size]
        encoded = tokenizer(
            batch_texts,
            add_special_tokens=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt",
            truncation=True,
        )
        input_ids      = encoded["input_ids"].to(device)
        attention_mask = encoded["attention_mask"].to(device)

        with torch.no_grad():
            outputs = biobert_model(input_ids, attention_mask=attention_mask)
            feats   = outputs.last_hidden_state  # [batch, max_length, 768]

        all_feats.append(feats.cpu())

    return torch.cat(all_feats, dim=0)  # [N, max_length, 768]


def train_cnn_biobert(
    training_data_path: pathlib.Path,
    weights_dir: pathlib.Path,
) -> None:
    """
    用 training_data.xlsx 训练 CNN_BioBERT 并保存权重。
    镜像 CNNeo_CNN_BioBERT.ipynb 全流程。

    注意：BioBERT 嵌入在 CPU 上较慢（训练集 ~thousands samples × BioBERT）。
    推荐在 GPU 服务器/HPC 上运行，或使用 --model fcnn_tf 替代。

    产出（weights_dir 下）：
      cnn_biobert_model.pth — 训练好的 TextCNN 权重
    """
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        print(
            "[run_cnneo][CNN_BioBERT] 需要 transformers 包：pip install transformers",
            file=sys.stderr,
        )
        raise

    print("[run_cnneo][CNN_BioBERT] 开始训练……（BioBERT 嵌入较慢，请耐心）", file=sys.stderr)
    print(f"[run_cnneo][CNN_BioBERT] 训练数据: {training_data_path}", file=sys.stderr)

    if not training_data_path.exists():
        print(
            f"[run_cnneo] ERROR: training_data 不存在: {training_data_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    data = pd.read_excel(training_data_path)
    required_cols = {"Mutated Peptide", "HLA type", "label"}
    missing = required_cols - set(data.columns)
    if missing:
        print(
            f"[run_cnneo] ERROR: training_data.xlsx 缺少列: {missing}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 镜像 notebook cell-1
    data["HLA type"] = data["HLA type"].astype(str).str.replace("*", "", regex=False)
    data["HLA type"] = data["HLA type"].str.replace(" ", "", regex=False)
    data["HLA type"] = data["HLA type"].str.replace("\xa0", "", regex=False)
    data["M"]        = data["Mutated Peptide"].astype(str).apply(pad_peptide)

    def _row_4mer(row: pd.Series) -> str:
        seq = str(row["HLA type"]) + str(row["M"])
        kmers = [seq[i : i + CNN_BB_KMER_SIZE].lower()
                 for i in range(len(seq) - CNN_BB_KMER_SIZE + 1)]
        return " ".join(kmers)

    data["trans"] = data.apply(_row_4mer, axis=1)
    y = data["label"].astype(int)

    # ------------------------------------------------------------------
    # BioBERT 嵌入（一次性，对全训练集）
    # ------------------------------------------------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(
        f"[run_cnneo][CNN_BioBERT] 使用设备: {device}",
        file=sys.stderr,
    )
    print(
        f"[run_cnneo][CNN_BioBERT] 加载 BioBERT: {CNN_BB_MODEL_NAME}（首次需下载 ~500MB）",
        file=sys.stderr,
    )
    tokenizer     = AutoTokenizer.from_pretrained(CNN_BB_MODEL_NAME)
    biobert_model = AutoModel.from_pretrained(CNN_BB_MODEL_NAME).to(device)

    features = _embed_biobert(
        list(data["trans"]), tokenizer, biobert_model,
        max_length=CNN_BB_MAX_LEN, device=device,
    )
    # features: [N, 64, 768]
    print(
        f"[run_cnneo][CNN_BioBERT] BioBERT 嵌入 shape: {features.shape}",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------
    # 切分数据集
    # ------------------------------------------------------------------
    torch.manual_seed(RANDOM_SEED)
    labels = torch.tensor(y.values, dtype=torch.long)

    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=RANDOM_SEED, stratify=labels
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, random_state=RANDOM_SEED, stratify=y_train
    )

    train_ds = TensorDataset(X_train, y_train)
    val_ds   = TensorDataset(X_val, y_val)

    train_loader = DataLoader(
        train_ds,
        batch_size=CNN_BB_BATCH_SIZE,
        shuffle=True,
        num_workers=0,
        pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=CNN_BB_BATCH_SIZE,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    # ------------------------------------------------------------------
    # 训练 TextCNN（镜像 notebook：epochs=19, lr=0.0001）
    # ------------------------------------------------------------------
    input_sz   = features.shape[2]   # 768
    cnn_model  = TextCNN(input_sz).to(device)
    criterion  = nn.CrossEntropyLoss()
    optimizer  = torch.optim.Adam(cnn_model.parameters(), lr=CNN_BB_LR)

    for epoch in range(CNN_BB_EPOCHS):
        cnn_model.train()
        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            outputs = cnn_model(inputs)
            loss    = criterion(outputs, targets)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        if (epoch + 1) % 5 == 0 or epoch == 0:
            cnn_model.eval()
            val_correct = 0
            val_total   = 0
            with torch.no_grad():
                for inputs, targets in val_loader:
                    inputs, targets = inputs.to(device), targets.to(device)
                    outputs = cnn_model(inputs)
                    _, predicted = torch.max(outputs, 1)
                    val_total   += targets.size(0)
                    val_correct += (predicted == targets).sum().item()
            print(
                f"[CNN_BioBERT] Epoch [{epoch+1}/{CNN_BB_EPOCHS}] "
                f"ValAcc={100*val_correct/val_total:.2f}%",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # 保存权重
    # ------------------------------------------------------------------
    weights_dir.mkdir(parents=True, exist_ok=True)
    model_path = weights_dir / "cnn_biobert_model.pth"
    torch.save(cnn_model.state_dict(), model_path)
    print(f"[run_cnneo][CNN_BioBERT] 权重已保存: {model_path}", file=sys.stderr)


def run_inference_cnn_biobert(
    input_csv: pathlib.Path,
    output_csv: pathlib.Path,
    model_path: pathlib.Path,
    smoke: int = 0,
    batch_size: int = 64,
) -> None:
    """
    CNN_BioBERT 推理：读 cnneo_input.csv → 输出 cnneo_raw_output.csv。
    """
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        print(
            "[run_cnneo][CNN_BioBERT] 需要 transformers 包：pip install transformers",
            file=sys.stderr,
        )
        raise

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(
        f"[run_cnneo][CNN_BioBERT] 加载 BioBERT: {CNN_BB_MODEL_NAME}",
        file=sys.stderr,
    )
    tokenizer     = AutoTokenizer.from_pretrained(CNN_BB_MODEL_NAME)
    biobert_model = AutoModel.from_pretrained(CNN_BB_MODEL_NAME).to(device)

    # 加载 TextCNN
    cnn_model = TextCNN(input_size=768)
    cnn_model.load_state_dict(torch.load(model_path, map_location=device))
    cnn_model = cnn_model.to(device)
    cnn_model.eval()
    print(f"[run_cnneo][CNN_BioBERT] TextCNN 已加载: {model_path}", file=sys.stderr)

    # ------------------------------------------------------------------
    # 读输入
    # ------------------------------------------------------------------
    if not input_csv.exists():
        print(
            f"[run_cnneo] ERROR: 输入文件不存在: {input_csv}",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_csv(input_csv, dtype=str)
    df["peptide"] = df["peptide"].str.strip()
    df["hla"]     = df["hla"].str.strip()

    if smoke > 0:
        df = df.head(smoke)
        print(
            f"[run_cnneo][CNN_BioBERT] --smoke {smoke}：只推理前 {smoke} 行",
            file=sys.stderr,
        )

    n_total = len(df)
    print(f"[run_cnneo][CNN_BioBERT] 待推理 {n_total} 个 (peptide, hla) 对", file=sys.stderr)

    # ------------------------------------------------------------------
    # 预处理 + BioBERT 嵌入
    # ------------------------------------------------------------------
    trans_texts = build_kmer_texts(df, k=CNN_BB_KMER_SIZE)
    features    = _embed_biobert(
        trans_texts, tokenizer, biobert_model,
        max_length=CNN_BB_MAX_LEN, batch_size=batch_size, device=device,
    )

    infer_ds     = InferenceDataset(features)
    infer_loader = DataLoader(
        infer_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    # ------------------------------------------------------------------
    # TextCNN 推理
    # ------------------------------------------------------------------
    all_scores = []
    with torch.no_grad():
        for batch_X in infer_loader:
            batch_X = batch_X.to(device)
            logits  = cnn_model(batch_X)
            probs   = F.softmax(logits, dim=1)
            scores  = probs[:, 1].cpu().numpy()
            all_scores.append(scores)

    scores_arr = np.concatenate(all_scores)
    labels_arr = (scores_arr > 0.5).astype(int)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    result_df = df[["peptide", "hla"]].copy()
    result_df["score"] = scores_arr
    result_df["label"] = labels_arr
    result_df.to_csv(output_csv, index=False, encoding="utf-8")

    print(
        f"[run_cnneo][CNN_BioBERT] 推理完成，共 {n_total} 对，label=1: {int(labels_arr.sum())}",
        file=sys.stderr,
    )
    print(f"[run_cnneo][CNN_BioBERT] 输出: {output_csv}", file=sys.stderr)


# ============================================================================
# CLI
# ============================================================================

def parse_args() -> argparse.Namespace:
    script_dir    = pathlib.Path(__file__).parent
    repo_root     = script_dir.parents[2]   # QuantImmuBench/
    newtools_dir  = repo_root / "scripts" / "out" / "newtools"
    weights_dir   = script_dir / "weights"
    training_data = script_dir / "repo" / "training_data" / "training_data.xlsx"

    parser = argparse.ArgumentParser(
        description=(
            "CNNeo/CNNeoPP 推理脚本（FCNN_TF 默认；--model cnn_biobert 切换旗舰模型）\n"
            "首次运行自动从 training_data.xlsx 训练。"
        )
    )
    parser.add_argument(
        "--model",
        choices=["fcnn_tf", "cnn_biobert"],
        default="fcnn_tf",
        help="子模型（默认 fcnn_tf：CPU 友好；cnn_biobert：旗舰，需 transformers）",
    )
    parser.add_argument(
        "--input-csv",
        default=str(newtools_dir / "cnneo_input.csv"),
        help="prep_input.py 产生的 cnneo_input.csv（列：peptide, hla）",
    )
    parser.add_argument(
        "--output-csv",
        default=str(newtools_dir / "cnneo_raw_output.csv"),
        help="输出路径（列：peptide, hla, score, label）",
    )
    parser.add_argument(
        "--weights-dir",
        default=str(weights_dir),
        help="权重保存/加载目录（默认 HPC/deploy/cnneo/weights/）",
    )
    parser.add_argument(
        "--training-data",
        default=str(training_data),
        help="training_data.xlsx 路径（默认 repo/training_data/training_data.xlsx）",
    )
    parser.add_argument(
        "--force-retrain",
        action="store_true",
        help="即使权重已存在也强制重新训练",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测：只推理前 N 个 (peptide, hla) 对（0=全量；训练仍用完整数据）",
    )
    return parser.parse_args()


def main() -> None:
    args          = parse_args()
    input_csv     = pathlib.Path(args.input_csv)
    output_csv    = pathlib.Path(args.output_csv)
    weights_dir   = pathlib.Path(args.weights_dir)
    training_data = pathlib.Path(args.training_data)

    print(f"[run_cnneo] 模型    : {args.model}", file=sys.stderr)
    print(f"[run_cnneo] 输入    : {input_csv}", file=sys.stderr)
    print(f"[run_cnneo] 输出    : {output_csv}", file=sys.stderr)
    print(f"[run_cnneo] 权重目录: {weights_dir}", file=sys.stderr)

    if args.model == "fcnn_tf":
        model_path      = weights_dir / "fcnn_tf_model.pth"
        vectorizer_path = weights_dir / "fcnn_tf_vectorizer.pkl"

        weights_exist = model_path.exists() and vectorizer_path.exists()
        if args.force_retrain or not weights_exist:
            if args.force_retrain:
                print("[run_cnneo] --force-retrain：强制重新训练", file=sys.stderr)
            else:
                print(
                    "[run_cnneo] 权重不存在，自动开始训练 FCNN_TF……",
                    file=sys.stderr,
                )
            train_fcnn_tf(training_data, weights_dir)
        else:
            print("[run_cnneo][FCNN_TF] 权重已存在，跳过训练", file=sys.stderr)

        run_inference_fcnn_tf(
            input_csv, output_csv, model_path, vectorizer_path, smoke=args.smoke
        )

    elif args.model == "cnn_biobert":
        model_path = weights_dir / "cnn_biobert_model.pth"

        if args.force_retrain or not model_path.exists():
            if args.force_retrain:
                print("[run_cnneo] --force-retrain：强制重新训练", file=sys.stderr)
            else:
                print(
                    "[run_cnneo] 权重不存在，自动开始训练 CNN_BioBERT……",
                    file=sys.stderr,
                )
            train_cnn_biobert(training_data, weights_dir)
        else:
            print("[run_cnneo][CNN_BioBERT] 权重已存在，跳过训练", file=sys.stderr)

        run_inference_cnn_biobert(
            input_csv, output_csv, model_path, smoke=args.smoke
        )

    print("[run_cnneo] 完成。", file=sys.stderr)


if __name__ == "__main__":
    main()
