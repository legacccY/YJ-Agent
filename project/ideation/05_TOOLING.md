# 工具层 — 撞车检测 + gap 挖掘工作流

> G1 去重 / G2 撞车检测 / S1 gap 挖掘 的可编程后端。全部免费 API 额度 + 本机 8GB 卡内可跑。
> 本文是**规格**：实际脚本 `tools/ideation_*.py` 派 `coder` 据此实现（主线不亲手写实验码）。
> 依据：1 路 researcher 联网采集，端点/额度均带引用，未核实处标 TODO。
>
> ✅ **已实现（2026-06-17）**：`tools/ideation_collision.py`（G2 撞车+G1 去重）、`tools/ideation_gapmine.py`（S1 gap）、`tools/test_ideation_tools.py`（pytest 30 passed/2 skipped）。
> **跑前需主线装依赖**：`pip install transformers adapters faiss-cpu torch`（collision 主路径）；`bertopic` 可选（gapmine 主路径，装不上自动降级 sklearn KMeans / TF-IDF）。SPECTER2 不可用时 collision 自动降级 OpenAlex API（无 GPU 可跑，余弦为估算仅初筛）。
> **未核实 TODO**：OpenAlex `/find/works` beta 端点行为 + 2026-02 起需免费 key；`specter2_adhoc_query` adapter 路径；4070 峰值 VRAM（首跑 `nvidia-smi` 实测）。

---

## 1. 免费文献 API（批量自动化）

| API | key | 限速 | 能力 | 用在哪 |
|---|---|---|---|---|
| **Semantic Scholar** | 免费申请（无 key 走共享池）| 有 key 1 req/s | search / batch / **recommendations**(相似论文,最多500) | G2 撞车检索 |
| **OpenAlex** | 2026-02 起需免费 key | $1/day credit（单 work 查询免费）| `/find/works` **语义相似搜索**(贴 abstract) + `related_works` | G2 撞车 / gap |
| **arXiv** | 无 | 1 req/3s | search + **OAI-PMH 批量**拉 category 近 N 年 | S1 gap 挖掘原料 |
| **Crossref** | 无（带 mailto polite pool）| 10 req/interval | 元数据/引用 | 补 venue/引用 |

端点：
- S2: `https://api.semanticscholar.org/graph/v1/paper/search` + `POST /recommendations/v1/papers`
- OpenAlex 语义搜：`/find/works`（贴 idea abstract，返回 embedding 相似排序，beta）
- arXiv 批量：`http://export.arxiv.org/oai2?verb=ListRecords&set=cs.CV&metadataPrefix=arXiv`

---

## 2. `tools/ideation_collision.py`（G1 去重 + G2 撞车检测）

**职责**：给一批候选（title+abstract 形式）算两两余弦去重 + 与已发论文库撞车相似度。

**实现规格**（SPECTER2 本地，8GB 卡足够）：
```python
# 依赖: pip install transformers adapters faiss-cpu torch
from transformers import AutoTokenizer
from adapters import AutoAdapterModel
import torch, torch.nn.functional as F

tok = AutoTokenizer.from_pretrained('allenai/specter2_base')
model = AutoAdapterModel.from_pretrained('allenai/specter2_base')
model.load_adapter("allenai/specter2", source="hf", load_as="proximity", set_active=True)
model.eval().cuda()  # BERT-base ~110M, fp32 推理 ~1.5-2GB VRAM, batch 512/次

def embed(papers):  # papers=[{title, abstract}]
    texts = [p['title'] + tok.sep_token + (p.get('abstract') or '') for p in papers]
    inp = tok(texts, padding=True, truncation=True, max_length=512, return_tensors='pt').to('cuda')
    with torch.no_grad():
        return model(**inp).last_hidden_state[:, 0, :]  # CLS, [N,768]
```
- **G1 去重**：候选间余弦 > 0.8 → 合并（Stanford 阈）。
- **G2 撞车**：候选 vs 已发库（S2 拉核心 keyword 近 3 年 ~500-2000 篇 → FAISS 索引）→ top-K 余弦；>0.85 红色警报，0.80-0.85 人工判。
- 注：SPECTER2 用 `adhoc_query` adapter 转 idea 文本、`proximity` adapter 转库论文，官方推荐混用检索更准。
- TODO：4070 上确切峰值 VRAM 官方未给，首次跑 `nvidia-smi` 实测。

**轻量备选**：OpenAlex `/find/works` 贴 abstract 直接返相似论文，不需本地 GPU，免费额度内，可作快速初筛。

---

## 3. `tools/ideation_gapmine.py`（S1 future-work gap 挖掘）

**职责**：从近 2 年顶会论文 limitation/future-work 段批量挖未解问题，聚类成候选 gap。

**实现规格**：
1. arXiv OAI-PMH 按 category（cs.CV/cs.LG/q-bio…）拉近 2 年元数据 + abstract。
2. 有 open-access PDF 的用 `grobid`（开源）或 AllenAI Science Parse 提 section 文本。
3. regex 截 `(Future Work|Limitations|Conclusion)` section → 句级过滤 `we plan to|future work|one limitation|left for future`。
4. BERTopic 对抽出句子聚类 → 高频未解 topic cluster = 候选 gap。
5. SPECTER2 算各 gap cluster centroid，喂 G1 的 S1 ideator 当原料。

依据：BAGELS [arXiv:2505.18207](https://arxiv.org/pdf/2505.18207) / FutureGen [arXiv:2503.16561](https://arxiv.org/html/2503.16561v1) / BERTopic gap 检测 [JMIR](https://formative.jmir.org/2024/1/e49411)。

---

## 4. 落地工作流（8GB + 免费额度内，分层省成本）

```
快速初筛(5min,纯API免费): S2 search + OpenAlex /find/works 贴 abstract → 看有无明显撞车
中等(30min,本地SPECTER2): S2 拉近3年同keyword ~500-2000篇 → FAISS → top-K 余弦
gap挖掘(2h): arXiv OAI-PMH → grobid → regex future-work → BERTopic 聚类
反驳检验(可选,scite付费): 查 baseline 论文 citing context 有无人已声称做了
```

---

## 5. coder 交接清单

派 coder 实现时给：
- 本规格 + `.portfolio/datasets.json`（已有数据真源）
- Windows 规范（spawn/路径/OMP，见 [[feedback_windows_training]]）
- 输出对齐 `04_POOL.schema.md` 的 `g2_collision` 字段
- 先写 `ideation_collision.py`（G2 必需）→ pytest 自测 → 再 `ideation_gapmine.py`（S1 增强，非阻塞）
- 不启训练 / 不调外部付费 API（scite 等留 TODO）

> 工具未实现前，G2 撞车检测可降级人工：researcher 用 firecrawl/WebSearch + Semantic Scholar 网页版逐条查 top 候选，慢但能跑通流程。
