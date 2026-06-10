# E9 — FiLM vs Cross-Attention Quality-Conditioning（架构消融）准备

**状态（会话 24 更新）：代码已就绪。** 模型已支持 cross-attention conditioning（smoke 验过），v7 config 已建，resume 改 strict=False 解决跨 conditioning 暖启。**唯一剩余 = HPC 提交训练（gated on v6 训完，串行红线）。** 下方 §1 的旧「不支持」判断保留作改动前快照。

---

## 1. 现状判断（关键结论）

读了 `project/models/visienhance.py`（VisiEnhanceNet 全部）：

- 唯一的 quality-conditioning 机制是 `FiLMLayer`（`models/visienhance.py:84-115`），
  在每个 encoder/mid/decoder stage 后调用，用 `q_defect = 1-q` 通过两个 MLP
  生成 per-channel `(γ, β)` 做 `(1+film_scale·γ)*feat + film_scale·β`。
- `VisiEnhanceNet.__init__` / `forward` 完全围绕 `FiLMLayer` 硬编码，
  没有任何 `conditioning` 字段、没有 dispatch 逻辑、没有 cross-attention 模块。
- `train_visienhance.py:452-459` 构造模型时只传 `film_hidden` / `film_scale`，
  没有可切换的 conditioning 类型参数。
- E8（noFiLM 消融，`visienhance_s1_planA_256_noFiLM_hpc.yaml`）能跑，是因为
  `film_scale=0.0` 让 FiLM 退化为恒等映射 —— 这是"关掉"FiLM 的取巧法，
  不是切换到另一种 conditioning。E9 如果照搬这套路（比如硬把 q 向量
  cat 到 bottleneck token 里做 attention）**模型代码里完全没有这个分支**。

**结论：E9 现在不能通过改 config 跑，必须先在 `models/visienhance.py` 里新增
`CrossAttnConditioning` 模块 + dispatch 逻辑。**

---

## 2. 需要的代码改动（模型侧，未做，仅设计）

### 2.1 新模块：`CrossAttnFiLM` 或 `CrossAttnConditioning`

设计草案（放在 `models/visienhance.py`，与 `FiLMLayer` 平级）：

```python
class CrossAttnConditioning(nn.Module):
    """Quality defect vector q_defect attends into spatial feature map via
    cross-attention (q_defect as query, feature map tokens as KV; or
    feature map as query, q_defect-derived token as KV — 需定下方向).

    Two plausible designs:
      (A) q_defect (1 token) as Query, feature spatial positions (HW tokens)
          as Key/Value -> output 1 context vector -> broadcast-add/FiLM-style
          modulate (类似 SE block 的 attention 加权版本)
      (B) feature spatial positions as Query, q_defect projected to K/V
          tokens (e.g. 1 or few learned "quality tokens") -> standard
          cross-attention, output same shape as feature map, residual add.

    设计 (B) 更接近"标准 cross-attention conditioning"语义，建议采用。
    """

    def __init__(self, q_dim: int, channels: int, n_heads: int = 4, hidden: int = 128):
        super().__init__()
        self.q_proj = nn.Linear(q_dim, channels)  # q_defect -> 1 KV token
        self.attn = nn.MultiheadAttention(embed_dim=channels, num_heads=n_heads, batch_first=True)
        self.out_proj = nn.Conv2d(channels, channels, 1, bias=True)
        nn.init.zeros_(self.out_proj.weight)
        nn.init.zeros_(self.out_proj.bias)

    def forward(self, feat, q_defect):
        B, C, H, W = feat.shape
        tokens = feat.flatten(2).transpose(1, 2)          # [B, HW, C]  query
        kv = self.q_proj(q_defect).unsqueeze(1)            # [B, 1, C]   key=value
        attn_out, _ = self.attn(tokens, kv, kv)            # [B, HW, C]
        attn_out = attn_out.transpose(1, 2).reshape(B, C, H, W)
        return feat + self.out_proj(attn_out)              # zero-init residual
```

要点：
- 输出层 zero-init，初始近恒等，和 FiLM 的"film_scale 小 + zero-init"
  哲学一致，保证 resume/比较公平。
- `n_heads` 需整除 `channels`（各 stage channel 不同：64/128/256，
  4 heads 都能整除，OK）。

### 2.2 dispatch 逻辑

`VisiEnhanceNet.__init__` 新增参数 `conditioning: str = "film"`，
按值构造 `enc_films` / `mid_film` / `dec_films` 为 `FiLMLayer` 或
`CrossAttnConditioning`。`forward` 的调用签名两者一致
(`module(feat, qd)` -> 同 shape tensor)，所以 `forward` 主体代码
**不需要改**，只改 `__init__` 里 ModuleList 的构造分支。

`train_visienhance.py:452-459` 增加：
```python
conditioning=mcfg.get("conditioning", "film"),
```

### 2.3 测试

`project/tests/test_visienhance.py` 需加一条 cross-attn 路径的
forward shape / 梯度检查（对照现有 FiLM 测试写法）。

---

## 3. Config 字段设计（代码就绪后即可用）

新增 `project/configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml`，
以 v5 (`visienhance_s2_planA_256_v5_hpc.yaml`) 为基线，唯一改动：

```yaml
model:
  base_channels: 64
  enc_blocks: [2, 2, 2]
  mid_blocks: 6
  dec_blocks: [2, 2, 2]
  conditioning: crossattn   # ← 新增字段, film -> crossattn
  crossattn_heads: 4        # ← 新增, CrossAttnConditioning n_heads
  # film_hidden / film_scale 字段对 crossattn 分支无效, 可保留供 film 对照用
```

其余 `data` / `train` / `loss` / `frozen_models` / `output` / `wandb`
全部与 v5 相同（只改 `output.checkpoint_dir` 和 `wandb.name` 为
`*_v7_crossattn` 避免覆盖 v5 ckpt）。保持其余超参全同 v5 是为了
E9 对比的公平性（唯一变量 = conditioning 机制）。

---

## 4. 训练命令（代码就绪后）

与 v5 相同的 launcher，只换 config：

```bash
# resume 仍从 stage1_planA_256 best (与 v5 相同起点, 公平对比)
python train_visienhance.py --config configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml
```

---

## 5. 评估

复用 E8 的 FiLM 消融评估管线 `project/run_eval_filmabl_hpc.py`
（基于 `eval_diag_paired.py` 的严格配对协议）。需要小改：

- `run_eval_filmabl_hpc.py` 里的 `load_with_filmscale` 是按路径含
  `"noFiLM"` 字符串选 `film_scale`。E9 改为按路径含 `"crossattn"`
  选择 `conditioning="crossattn"` 构造 `VisiEnhanceNet`（同样靠
  monkeypatch `P.load_visienhance`）。
- `E.CKPTS` 字典改为：
  ```python
  E.CKPTS = {
      "FiLM (v5)":       f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth",
      "CrossAttn (v7)":  f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v7_crossattn/best_visienhance.pth",
  }
  ```
- 输出指标对齐 E1（PSNR/SSIM）+ E5（dAUC/一致率/dangerous_flip/KL），
  与现有 v5 vs v6 比较表同格式。

---

## 6. TODO 清单（按执行顺序）

1. [x] `models/visienhance.py`：新增 `CrossAttnConditioning` 类（n_tokens=4 quality token，feature 做 query，zero-init 残差。**修正草案缺陷**：单 KV token 退化成全局偏置非真注意力 → 改 4 token）
2. [x] `models/visienhance.py`：`VisiEnhanceNet.__init__` 加 `conditioning`/`crossattn_heads` 参数 + `_make_conditioning` dispatch（默认 film，后向兼容）
3. [x] `train_visienhance.py`：传入 `conditioning`/`crossattn_heads` + resume 改 **strict=False**（跨 conditioning 暖启 backbone、conditioning 留 init；FiLM→FiLM 仍 0/0 全加载）
4. [ ] `tests/test_visienhance.py`：加 cross-attn 测试（smoke 已覆盖 forward/grad/init/resume，正式 test 可选）
5. [x] 建 `configs/visienhance_s2_planA_256_v7_crossattn_hpc.yaml`（= v5 + conditioning:crossattn，唯一变量）
6. [ ] 改 `run_eval_filmabl_hpc.py` → E9 launcher（§5，eval 时做，需 v7 ckpt 路径）
7. [ ] HPC 提交训练（**gated on v6 训完，串行红线**）；提交前重传 `models/visienhance.py`+`train_visienhance.py`+v7 config 到 HPC

**当前完成度：4/7（核心代码全就绪，smoke 验过；剩 eval launcher + HPC 提交，后者 gated on v6）。**

## 7. Smoke 验证记录（会话 24，本地 CPU）
- film: out (2,3,64,64) 15.33M、grad finite、init |out-x|=0（近恒等）✓
- crossattn: out (2,3,64,64) 17.17M（+1.84M）、grad finite、init |out-x|=0 ✓
- 默认 conditioning='film' → 后向兼容 v5/v6 ✓
- resume crossattn←FiLM: 70 missing/56 unexpected 全是 conditioning 模块、**backbone 0 missing** ✓；FiLM←FiLM 0/0 ✓
