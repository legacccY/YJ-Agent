"""
pytest 测试：ideation_collision.py + ideation_gapmine.py
=========================================================
覆盖：
- embed() 输出维度
- dedup() 合并映射正确
- collision() schema 对齐 04_POOL.schema.md
- 降级路径触发（monkeypatch SPECTER2 → collision_openalex）
- extract_fw_sentences() 正则正确
- cluster_sentences() TF-IDF 降级路径可运行
- fetch_corpus() / fetch_arxiv_abstracts() → mock 网络

真模型下载: 标 @pytest.mark.needs_model，无模型/无网跳过。
网络请求: 全部 monkeypatch，不发真实 HTTP。
"""

from __future__ import annotations

import json
import pathlib
import sys
import importlib
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# 将 tools/ 加入路径
sys.path.insert(0, str(pathlib.Path(__file__).parent))

# ── mock 候选论文（手写，不走网络）────────────────────────────────────────────
MOCK_CANDIDATES = [
    {
        "id": "C001",
        "title": "Uncertainty-Aware Medical Image Segmentation with Self-Supervised Learning",
        "abstract": "We propose a self-supervised method for medical image segmentation that incorporates uncertainty estimation. Our approach achieves state-of-the-art results on multiple benchmarks.",
        "status": "alive",
    },
    {
        "id": "C002",
        "title": "Self-Supervised Uncertainty Estimation for Medical Image Segmentation",
        "abstract": "A self-supervised framework for segmenting medical images with built-in uncertainty quantification. We evaluate on chest X-ray and skin lesion datasets.",
        "status": "alive",
    },
    {
        "id": "C003",
        "title": "Neural Cellular Automata for Pathology Slide Analysis",
        "abstract": "We apply neural cellular automata to whole-slide image analysis in computational pathology. The model achieves emergent global segmentation via local update rules.",
        "status": "alive",
    },
    {
        "id": "C004",
        "title": "Diffusion Models for Anomaly Detection in Chest Radiographs",
        "abstract": "We introduce a diffusion-based anomaly detection framework for chest X-rays. The model generates healthy reconstructions and detects anomalies via pixel-level residuals.",
        "status": "alive",
    },
]

MOCK_CORPUS = [
    {
        "title": "Self-Supervised Medical Image Segmentation with Uncertainty Quantification",
        "abstract": "Prior work on self-supervised segmentation with uncertainty for medical imaging.",
        "year": 2024,
        "paperId": "paper_001",
    },
    {
        "title": "Anomaly Detection in Radiology via Generative Models",
        "abstract": "Using VAE and GAN for anomaly detection in radiology images.",
        "year": 2024,
        "paperId": "paper_002",
    },
    {
        "title": "Transformer-Based Fundus Image Classification",
        "abstract": "Vision transformer applied to fundus photographs for diabetic retinopathy grading.",
        "year": 2025,
        "paperId": "paper_003",
    },
]

MOCK_FW_SENTENCES = [
    "Future work will extend this to multi-modal settings.",
    "One limitation of our approach is the computational cost.",
    "We plan to investigate larger datasets in future studies.",
    "This remains an open problem in the medical imaging community.",
    "We leave the exploration of 3D volumetric data for future work.",
    "Promising directions include extending to video sequences.",
    "Our method could be extended to handle real-time inference.",
]


# ══════════════════════════════════════════════════════════════════════════════
# 工具：构造 fake L2-归一化 embedding 矩阵
# ══════════════════════════════════════════════════════════════════════════════

def make_fake_vecs(n: int, dim: int = 768, seed: int = 0) -> np.ndarray:
    """生成 N 条随机 L2-归一化向量，模拟 SPECTER2 输出。"""
    rng = np.random.RandomState(seed)
    v = rng.randn(n, dim).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
    return v


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 1：cosine 工具函数（无依赖）
# ══════════════════════════════════════════════════════════════════════════════

def test_cosine_matrix_shape():
    """_cosine_matrix 返回正确形状 [N, M]。"""
    from ideation_collision import _cosine_matrix

    a = make_fake_vecs(4)   # [4, 768]
    b = make_fake_vecs(6)   # [6, 768]
    sim = _cosine_matrix(a, b)
    assert sim.shape == (4, 6), f"期望 (4, 6)，得到 {sim.shape}"


def test_cosine_self_similarity():
    """自身余弦相似度应为 1（L2 归一化后内积 = 1）。"""
    from ideation_collision import _cosine_matrix

    a = make_fake_vecs(5)
    sim = _cosine_matrix(a, a)
    diag = np.diag(sim)
    np.testing.assert_allclose(diag, np.ones(5), atol=1e-5,
                               err_msg="自身余弦相似度应为 1")


def test_cosine_range():
    """余弦相似度值域 [-1, 1]。"""
    from ideation_collision import _cosine_matrix

    a = make_fake_vecs(10)
    b = make_fake_vecs(10, seed=99)
    sim = _cosine_matrix(a, b)
    assert sim.min() >= -1.0 - 1e-5 and sim.max() <= 1.0 + 1e-5, \
        f"余弦值域超出 [-1,1]：min={sim.min()}, max={sim.max()}"


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 2：embed() —— mock SPECTER2
# ══════════════════════════════════════════════════════════════════════════════

class MockSPECTER2Output:
    """模拟 transformers 模型输出。"""
    def __init__(self, n: int, dim: int = 768):
        import torch
        self.last_hidden_state = torch.from_numpy(
            make_fake_vecs(n, dim)[np.newaxis]  # 先构造，再调整
        )
        # 实际应为 [B, seq_len, dim]，CLS 在 index 0
        self.last_hidden_state = torch.from_numpy(
            np.random.randn(n, 16, dim).astype(np.float32)
        )
        # 替换 CLS（index 0）为已知向量
        cls_vecs = make_fake_vecs(n, dim)
        self.last_hidden_state[:, 0, :] = torch.from_numpy(cls_vecs)


def _mock_specter2_setup(monkeypatch):
    """将 SPECTER2 全局状态 mock 为可用，注入 fake 模型。"""
    import ideation_collision as ic

    # 重置全局状态
    monkeypatch.setattr(ic, "_specter2_available", True)

    # mock tokenizer
    fake_tok = MagicMock()
    fake_tok.sep_token = "[SEP]"
    fake_tok.return_value = {
        "input_ids": MagicMock(),
        "attention_mask": MagicMock(),
    }
    monkeypatch.setattr(ic, "_specter2_tok", fake_tok)

    # mock model: 对任意输入返回 fake hidden state
    def fake_model_call(**kwargs):
        # 从 input_ids 猜 batch size（kwargs 是 mock 对象，用固定 n=len 候选）
        return MockSPECTER2Output(n=4)  # batch size 4

    fake_model = MagicMock()
    fake_model.__call__ = MagicMock(side_effect=fake_model_call)
    fake_model.return_value = MockSPECTER2Output(n=4)
    monkeypatch.setattr(ic, "_specter2_model", fake_model)
    monkeypatch.setattr(ic, "_specter2_query_model", fake_model)
    monkeypatch.setattr(ic, "_device", "cpu")

    return fake_tok, fake_model


def test_embed_output_shape(monkeypatch):
    """embed() 返回 [N, 768] float32 numpy array（mock SPECTER2）。"""
    import torch
    import ideation_collision as ic

    monkeypatch.setattr(ic, "_specter2_available", True)
    monkeypatch.setattr(ic, "_device", "cpu")

    # 构造 fake tokenizer
    fake_tok = MagicMock()
    fake_tok.sep_token = "[SEP]"
    n = len(MOCK_CANDIDATES[:3])

    # fake tokenizer 返回 dict of tensors
    fake_input = {
        "input_ids": torch.zeros((n, 16), dtype=torch.long),
        "attention_mask": torch.ones((n, 16), dtype=torch.long),
    }
    fake_tok.return_value = fake_input
    monkeypatch.setattr(ic, "_specter2_tok", fake_tok)

    # fake model 返回正确 shape hidden state
    class FakeModelOut:
        def __init__(self, n):
            self.last_hidden_state = torch.from_numpy(
                np.random.randn(n, 16, 768).astype(np.float32)
            )

    fake_model = MagicMock()
    fake_model.return_value = FakeModelOut(n)
    fake_model.__call__ = MagicMock(return_value=FakeModelOut(n))
    monkeypatch.setattr(ic, "_specter2_model", fake_model)
    monkeypatch.setattr(ic, "_specter2_query_model", fake_model)

    papers = MOCK_CANDIDATES[:3]
    vecs = ic.embed(papers, use_query_adapter=False)

    assert isinstance(vecs, np.ndarray), "embed() 应返回 np.ndarray"
    assert vecs.shape == (n, 768), f"期望 ({n}, 768)，得到 {vecs.shape}"
    assert vecs.dtype == np.float32, f"期望 float32，得到 {vecs.dtype}"


def test_embed_l2_normalized(monkeypatch):
    """embed() 输出应为 L2 归一化（范数约为 1）。"""
    import torch
    import ideation_collision as ic

    monkeypatch.setattr(ic, "_specter2_available", True)
    monkeypatch.setattr(ic, "_device", "cpu")

    n = 2
    fake_tok = MagicMock()
    fake_tok.sep_token = "[SEP]"
    fake_tok.return_value = {
        "input_ids": torch.zeros((n, 16), dtype=torch.long),
        "attention_mask": torch.ones((n, 16), dtype=torch.long),
    }
    monkeypatch.setattr(ic, "_specter2_tok", fake_tok)

    # 用非归一化向量测试归一化
    raw_vecs = np.array([[3.0, 4.0] + [0.0] * 766,
                          [1.0, 0.0] + [0.0] * 766], dtype=np.float32)

    class FakeOut:
        def __init__(self):
            import torch
            full = np.zeros((n, 16, 768), dtype=np.float32)
            full[:, 0, :] = raw_vecs
            self.last_hidden_state = torch.from_numpy(full)

    fake_model = MagicMock()
    fake_model.return_value = FakeOut()
    monkeypatch.setattr(ic, "_specter2_model", fake_model)
    monkeypatch.setattr(ic, "_specter2_query_model", fake_model)

    vecs = ic.embed(MOCK_CANDIDATES[:2], use_query_adapter=False)
    norms = np.linalg.norm(vecs, axis=1)
    np.testing.assert_allclose(norms, np.ones(n), atol=1e-5,
                               err_msg="embed() 输出应 L2 归一化")


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 3：dedup()
# ══════════════════════════════════════════════════════════════════════════════

def test_dedup_identical_returns_one(monkeypatch):
    """两条完全相同的候选（cos=1）应被去重为一条。"""
    import ideation_collision as ic

    n = 2
    # C001 和 C002 给相同的向量 → cos = 1 → 去重
    same_vec = make_fake_vecs(1)  # [1, 768]
    identical_vecs = np.repeat(same_vec, n, axis=0)  # [2, 768]

    monkeypatch.setattr(ic, "_specter2_available", True)
    # patch embed：对所有输入返回相同向量
    monkeypatch.setattr(ic, "embed", lambda papers, **kw: identical_vecs[:len(papers)])

    dupes = [MOCK_CANDIDATES[0], MOCK_CANDIDATES[1]]
    deduped, merge_map = ic.dedup(dupes, thr=0.8)

    assert len(deduped) == 1, f"期望去重后 1 条，得到 {len(deduped)}"
    assert len(merge_map) == 1, f"期望 merge_map 有 1 条，得到 {merge_map}"


def test_dedup_dissimilar_keeps_all(monkeypatch):
    """4 条差异很大的候选应全部保留（cos < 0.8）。"""
    import ideation_collision as ic

    n = 4
    distinct_vecs = make_fake_vecs(n, seed=42)  # 随机向量，cos 通常很小

    monkeypatch.setattr(ic, "_specter2_available", True)
    monkeypatch.setattr(ic, "embed", lambda papers, **kw: distinct_vecs[:len(papers)])

    deduped, merge_map = ic.dedup(MOCK_CANDIDATES, thr=0.8)

    assert len(deduped) == n, f"期望保留全部 {n} 条，得到 {len(deduped)}"
    assert len(merge_map) == 0, f"期望无合并，得到 {merge_map}"


def test_dedup_empty():
    """空输入返回空列表和空映射。"""
    from ideation_collision import dedup

    deduped, merge_map = dedup([], thr=0.8)
    assert deduped == []
    assert merge_map == {}


def test_dedup_specter2_unavailable(monkeypatch):
    """SPECTER2 不可用时，dedup 跳过，返回原始候选。"""
    import ideation_collision as ic

    monkeypatch.setattr(ic, "_specter2_available", False)
    # 确保不调用真实模型加载
    monkeypatch.setattr(ic, "_try_load_specter2", lambda: False)

    deduped, merge_map = ic.dedup(MOCK_CANDIDATES, thr=0.8)

    assert len(deduped) == len(MOCK_CANDIDATES), "降级时应返回原始全部候选"
    assert merge_map == {}


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 4：collision() schema 正确
# ══════════════════════════════════════════════════════════════════════════════

def test_collision_schema_fields(monkeypatch):
    """collision() 返回的每条结果必须含 g2_collision 字段，且符合 schema。"""
    import ideation_collision as ic

    n_cand = len(MOCK_CANDIDATES)
    n_corpus = len(MOCK_CORPUS)

    monkeypatch.setattr(ic, "_specter2_available", True)

    # cand vecs: n_cand 条（稍微带点变化）
    cand_vecs = make_fake_vecs(n_cand, seed=1)
    # corpus vecs: n_corpus 条
    corpus_vecs = make_fake_vecs(n_corpus, seed=2)

    call_count = [0]

    def fake_embed(papers, use_query_adapter=False):
        call_count[0] += 1
        # 第一次调用 = corpus，第二次 = candidates
        n = len(papers)
        if use_query_adapter:
            return cand_vecs[:n]
        else:
            return corpus_vecs[:n]

    monkeypatch.setattr(ic, "embed", fake_embed)

    # patch faiss
    class FakeIndex:
        def __init__(self, dim): pass
        def add(self, vecs): pass
        def search(self, vecs, k):
            n = vecs.shape[0]
            # 返回假的 top-K 分数和索引
            scores = np.full((n, k), 0.6, dtype=np.float32)
            indices = np.zeros((n, k), dtype=np.int64)
            return scores, indices

    import types
    fake_faiss = types.ModuleType("faiss")
    fake_faiss.IndexFlatIP = FakeIndex

    monkeypatch.setitem(sys.modules, "faiss", fake_faiss)

    results = ic.collision(MOCK_CANDIDATES, MOCK_CORPUS, topk=3, thr=0.85)

    assert len(results) == n_cand, f"期望 {n_cand} 条结果，得到 {len(results)}"
    for r in results:
        g2 = r.get("g2_collision")
        assert g2 is not None, f"缺少 g2_collision 字段：{r.get('id')}"
        assert "max_cos" in g2, "g2_collision 缺 max_cos"
        assert "nearest" in g2, "g2_collision 缺 nearest"
        assert "source" in g2, "g2_collision 缺 source"
        assert isinstance(g2["max_cos"], float), "max_cos 应为 float"


def test_collision_red_alert(monkeypatch):
    """当 max_cos > thr 时，候选应被标记 g2_kill='撞车'。"""
    import ideation_collision as ic

    n_cand = 2
    n_corpus = 2
    monkeypatch.setattr(ic, "_specter2_available", True)

    # 制造高相似度：cand[0] 和 corpus[0] 完全相同向量
    shared_vec = make_fake_vecs(1, seed=7)  # [1, 768]
    cand_vecs = np.concatenate([shared_vec, make_fake_vecs(1, seed=99)], axis=0)
    corpus_vecs = np.concatenate([shared_vec, make_fake_vecs(1, seed=8)], axis=0)

    def fake_embed(papers, use_query_adapter=False):
        n = len(papers)
        if use_query_adapter:
            return cand_vecs[:n]
        return corpus_vecs[:n]

    monkeypatch.setattr(ic, "embed", fake_embed)

    class FakeIndex:
        def __init__(self, dim): pass
        def add(self, vecs):
            self._vecs = vecs
        def search(self, q_vecs, k):
            # 手动计算真实内积
            scores = (q_vecs @ self._vecs.T)  # [N, M]
            n = q_vecs.shape[0]
            # top-k: 取最高分
            top_scores = np.sort(scores, axis=1)[:, ::-1][:, :k]
            top_indices = np.argsort(scores, axis=1)[:, ::-1][:, :k]
            return top_scores.astype(np.float32), top_indices.astype(np.int64)

    import types
    fake_faiss = types.ModuleType("faiss")
    fake_faiss.IndexFlatIP = FakeIndex
    monkeypatch.setitem(sys.modules, "faiss", fake_faiss)

    candidates = MOCK_CANDIDATES[:n_cand]
    corpus = MOCK_CORPUS[:n_corpus]
    results = ic.collision(candidates, corpus, topk=1, thr=0.85)

    # cand[0] 与 corpus[0] 向量相同 → cos = 1.0 > 0.85 → 应标 g2_kill
    r0 = results[0]
    assert r0.get("g2_kill") == "撞车", \
        f"高相似度候选应被标 g2_kill='撞车'，实际：{r0.get('g2_kill')}"
    assert r0["g2_collision"]["max_cos"] > 0.85


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 5：降级路径 —— SPECTER2 加载失败 → collision_openalex
# ══════════════════════════════════════════════════════════════════════════════

def test_collision_fallback_to_openalex(monkeypatch):
    """SPECTER2 不可用时，collision() 应回退到 collision_openalex()。"""
    import ideation_collision as ic

    monkeypatch.setattr(ic, "_specter2_available", False)
    monkeypatch.setattr(ic, "_try_load_specter2", lambda: False)

    # mock collision_openalex 返回固定 schema
    mock_g2 = {"max_cos": 0.70, "nearest": "Mock Paper Title", "source": "openalex"}
    monkeypatch.setattr(ic, "collision_openalex", lambda cand, **kw: mock_g2)

    results = ic.collision(MOCK_CANDIDATES[:2], MOCK_CORPUS, topk=3, thr=0.85)

    assert len(results) == 2
    for r in results:
        g2 = r.get("g2_collision")
        assert g2 is not None
        assert g2["source"] == "openalex", "降级路径应标 source='openalex'"


def test_try_load_specter2_returns_false_on_import_error(monkeypatch):
    """当 transformers/adapters 不可导入时，_try_load_specter2 返回 False。"""
    import ideation_collision as ic

    # 重置全局状态
    monkeypatch.setattr(ic, "_specter2_available", None)
    monkeypatch.setattr(ic, "_specter2_model", None)
    monkeypatch.setattr(ic, "_specter2_tok", None)
    monkeypatch.setattr(ic, "_specter2_query_model", None)

    # 让 import torch 抛错
    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def broken_import(name, *args, **kwargs):
        if name in ("torch", "transformers", "adapters"):
            raise ImportError(f"mock: {name} not available")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=broken_import):
        # 重置再检测
        ic._specter2_available = None
        result = ic._try_load_specter2()

    assert result is False, "_try_load_specter2 应在导入失败时返回 False"
    assert ic._specter2_available is False


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 6：collision_openalex() schema
# ══════════════════════════════════════════════════════════════════════════════

def test_collision_openalex_schema(monkeypatch):
    """collision_openalex() 在 API 成功时返回正确 schema。"""
    import ideation_collision as ic

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "results": [
            {"title": "Nearest Paper Title", "id": "W123"},
            {"title": "Second Nearest", "id": "W456"},
        ]
    }
    fake_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=fake_resp):
        g2 = ic.collision_openalex(MOCK_CANDIDATES[0], topk=5)

    assert "max_cos" in g2
    assert "nearest" in g2
    assert "source" in g2
    assert g2["source"] == "openalex"
    assert isinstance(g2["max_cos"], float)
    assert g2["nearest"] == "Nearest Paper Title"


def test_collision_openalex_timeout(monkeypatch):
    """collision_openalex() 超时时返回 max_cos=0.0 不崩溃。"""
    import ideation_collision as ic
    import requests as req_module

    with patch("requests.get", side_effect=req_module.exceptions.Timeout("mock timeout")):
        g2 = ic.collision_openalex(MOCK_CANDIDATES[0])

    assert g2["max_cos"] == 0.0
    assert g2.get("error") == "timeout"


def test_collision_openalex_404(monkeypatch):
    """collision_openalex() 404 时返回 error='404' 不崩溃。"""
    import ideation_collision as ic

    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=fake_resp):
        g2 = ic.collision_openalex(MOCK_CANDIDATES[0])

    assert g2.get("error") == "404"


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 7：fetch_corpus() —— mock 网络
# ══════════════════════════════════════════════════════════════════════════════

def test_fetch_corpus_returns_papers(monkeypatch):
    """fetch_corpus() mock 网络，验证解析 S2 返回格式正确。"""
    import ideation_collision as ic

    fake_page1 = {
        "data": [
            {"title": "Paper A", "abstract": "Abstract A", "year": 2024, "paperId": "id_a"},
            {"title": "Paper B", "abstract": "Abstract B", "year": 2025, "paperId": "id_b"},
        ]
    }
    fake_page2 = {"data": []}  # 末页

    responses = [fake_page1, fake_page2]
    call_count = [0]

    def fake_get(url, params=None, headers=None, timeout=None):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = responses[min(call_count[0], len(responses)-1)]
        r.raise_for_status = MagicMock()
        call_count[0] += 1
        return r

    with patch("requests.get", side_effect=fake_get):
        papers = ic.fetch_corpus("medical segmentation", years=3, limit=100)

    assert len(papers) == 2
    assert papers[0]["title"] == "Paper A"
    assert papers[0]["source"] == "s2"


def test_fetch_corpus_429_retry(monkeypatch):
    """fetch_corpus() 遇 429 后退避重试，最终返回结果。"""
    import ideation_collision as ic

    call_count = [0]

    def fake_get(url, params=None, headers=None, timeout=None):
        r = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            # 第一次返回 429
            r.status_code = 429
            r.json.return_value = {}
            r.raise_for_status = MagicMock()
        else:
            r.status_code = 200
            r.json.return_value = {
                "data": [
                    {"title": "Paper X", "abstract": "Abs X", "year": 2025, "paperId": "x1"},
                ]
            }
            r.raise_for_status = MagicMock()
        return r

    with patch("requests.get", side_effect=fake_get):
        with patch("time.sleep"):  # 跳过真实等待
            papers = ic.fetch_corpus("test", years=1, limit=10)

    assert len(papers) >= 1, "429 退避后应成功获取论文"


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 8：JSONL 读写（无网络，纯文件 I/O）
# ══════════════════════════════════════════════════════════════════════════════

def test_load_save_jsonl(tmp_path):
    """load_jsonl / save_jsonl 往返测试。"""
    from ideation_collision import load_jsonl, save_jsonl

    items = [{"id": "A", "val": 1}, {"id": "B", "val": 2}]
    path = str(tmp_path / "test.jsonl")
    save_jsonl(items, path)
    loaded = load_jsonl(path)
    assert loaded == items


def test_load_jsonl_skip_bad_lines(tmp_path):
    """load_jsonl 跳过解析失败行，不崩溃。"""
    from ideation_collision import load_jsonl

    path = tmp_path / "bad.jsonl"
    path.write_text('{"id":"A"}\nnot json\n{"id":"C"}\n', encoding="utf-8")
    items = load_jsonl(str(path))
    assert len(items) == 2
    assert items[0]["id"] == "A"
    assert items[1]["id"] == "C"


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 9：gapmine —— extract_fw_sentences
# ══════════════════════════════════════════════════════════════════════════════

def test_extract_fw_sentences_matches():
    """extract_fw_sentences() 应匹配含 future-work 关键词的句子。"""
    from ideation_gapmine import extract_fw_sentences

    papers = [
        {
            "arxiv_id": "2401.00001",
            "title": "Test Paper",
            "abstract": "We propose a new method. Future work will extend this to 3D. Our approach is fast.",
            "year": 2024,
        },
        {
            "arxiv_id": "2401.00002",
            "title": "Another Paper",
            "abstract": "One limitation of our approach is memory usage. We plan to address this later.",
            "year": 2024,
        },
        {
            "arxiv_id": "2401.00003",
            "title": "Clean Paper",
            "abstract": "State-of-the-art results on all benchmarks. No limitations.",
            "year": 2024,
        },
    ]

    fw_items = extract_fw_sentences(papers)

    # 前两篇应有匹配，第三篇无
    ids_found = {item["arxiv_id"] for item in fw_items}
    assert "2401.00001" in ids_found, "应匹配 'Future work' 句"
    assert "2401.00002" in ids_found, "应匹配 'One limitation' 句"
    # 第三篇不含关键词
    # Note: "No limitations" 的 "limitation" 可能也被正则匹配，保守不断言其不在


def test_extract_fw_sentences_short_filter():
    """过短句子（< 20 字符）应被过滤。"""
    from ideation_gapmine import extract_fw_sentences

    papers = [{
        "arxiv_id": "x",
        "title": "T",
        "abstract": "Future work. We plan to do more. One limitation remains open.",
        "year": 2024,
    }]
    fw_items = extract_fw_sentences(papers)
    for item in fw_items:
        assert len(item["sentence"]) >= 20, f"句子过短：{item['sentence']!r}"


def test_extract_fw_sentences_empty():
    """空输入返回空列表。"""
    from ideation_gapmine import extract_fw_sentences

    assert extract_fw_sentences([]) == []


def test_extract_fw_no_abstract():
    """无 abstract 的论文不崩溃。"""
    from ideation_gapmine import extract_fw_sentences

    papers = [{"arxiv_id": "x", "title": "T", "abstract": "", "year": 2024}]
    result = extract_fw_sentences(papers)
    assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 10：gapmine —— cluster_sentences TF-IDF 降级
# ══════════════════════════════════════════════════════════════════════════════

def test_cluster_sentences_tfidf_fallback():
    """cluster_sentences(method='tfidf') 应正常运行，返回非空 cluster 列表。"""
    from ideation_gapmine import cluster_sentences

    # 构造 10+ 条 fw_items（TF-IDF 最少需要几条才能聚 k 类）
    fw_items = []
    for i, sent in enumerate(MOCK_FW_SENTENCES * 3):  # 21 条
        fw_items.append({
            "arxiv_id": f"id_{i:03d}",
            "title": f"Paper {i}",
            "year": 2024,
            "sentence": sent,
            "source_paper": {"title": f"Paper {i}", "arxiv_id": f"id_{i:03d}"},
        })

    clusters = cluster_sentences(fw_items, k=5, method="tfidf")

    assert len(clusters) > 0, "TF-IDF 降级聚类应返回非空结果"
    for c in clusters:
        assert "cluster_id" in c
        assert "size" in c
        assert "representative_sentences" in c
        assert "source_papers" in c
        assert "gap_summary" in c
        assert c["cluster_method"] == "tfidf_kmeans"


def test_cluster_sentences_empty():
    """空输入返回空列表。"""
    from ideation_gapmine import cluster_sentences

    result = cluster_sentences([], k=5, method="tfidf")
    assert result == []


def test_cluster_sentences_cluster_id_int():
    """cluster_id 应为 int（JSON 序列化友好）。"""
    from ideation_gapmine import cluster_sentences

    fw_items = []
    for i, sent in enumerate(MOCK_FW_SENTENCES * 2):
        fw_items.append({
            "arxiv_id": f"id_{i}",
            "title": "P",
            "year": 2024,
            "sentence": sent,
            "source_paper": {"title": "P", "arxiv_id": f"id_{i}"},
        })

    clusters = cluster_sentences(fw_items, k=3, method="tfidf")
    for c in clusters:
        assert isinstance(c["cluster_id"], int), \
            f"cluster_id 应为 int，得到 {type(c['cluster_id'])}"


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 11：gapmine —— format_gap_output schema
# ══════════════════════════════════════════════════════════════════════════════

def test_format_gap_output_schema():
    """format_gap_output() 返回符合 ideation pool S1-gap 策略的 schema。"""
    from ideation_gapmine import format_gap_output, cluster_sentences

    fw_items = []
    for i, sent in enumerate(MOCK_FW_SENTENCES * 2):
        fw_items.append({
            "arxiv_id": f"x{i}", "title": f"P{i}", "year": 2024,
            "sentence": sent,
            "source_paper": {"title": f"P{i}", "arxiv_id": f"x{i}"},
        })

    clusters = cluster_sentences(fw_items, k=3, method="tfidf")
    gaps = format_gap_output(clusters, "cs.CV", 2, 100, len(fw_items))

    assert len(gaps) > 0
    for g in gaps:
        assert g["strategy"] == "S1-gap"
        assert g["status"] == "alive"
        assert g["id"].startswith("GAP-")
        # pool schema 必须字段
        assert "one_liner" in g
        assert "problem" in g
        assert "datasets" in g
        assert "_meta" in g
        assert g["_meta"]["total_papers_scanned"] == 100


# ══════════════════════════════════════════════════════════════════════════════
# 测试组 12：gapmine —— arXiv OAI-PMH 解析（mock HTTP）
# ══════════════════════════════════════════════════════════════════════════════

_FAKE_OAI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
         xmlns:arxiv="http://arxiv.org/OAI/arXiv/">
  <ListRecords>
    <record>
      <metadata>
        <arxiv:arXiv>
          <arxiv:id>2401.00001</arxiv:id>
          <arxiv:title>Test Paper One</arxiv:title>
          <arxiv:abstract>We propose a method. Future work will extend this.</arxiv:abstract>
          <arxiv:categories>cs.CV cs.LG</arxiv:categories>
        </arxiv:arXiv>
      </metadata>
    </record>
    <record>
      <metadata>
        <arxiv:arXiv>
          <arxiv:id>2402.00002</arxiv:id>
          <arxiv:title>Test Paper Two</arxiv:title>
          <arxiv:abstract>Another method with limitations.</arxiv:abstract>
          <arxiv:categories>cs.CV</arxiv:categories>
        </arxiv:arXiv>
      </metadata>
    </record>
  </ListRecords>
</OAI-PMH>"""


def test_fetch_arxiv_mock():
    """fetch_arxiv_abstracts() mock OAI-PMH 响应，验证解析正确。"""
    from ideation_gapmine import fetch_arxiv_abstracts

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.text = _FAKE_OAI_XML
    fake_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=fake_resp):
        papers = fetch_arxiv_abstracts(category="cs.CV", years=2, limit=100)

    assert len(papers) == 2, f"期望 2 篇，得到 {len(papers)}"
    assert papers[0]["arxiv_id"] == "2401.00001"
    assert papers[0]["title"] == "Test Paper One"
    assert papers[1]["arxiv_id"] == "2402.00002"


def test_fetch_arxiv_503_retry():
    """fetch_arxiv_abstracts() 遇 503 时等待后重试。"""
    from ideation_gapmine import fetch_arxiv_abstracts

    call_count = [0]

    def fake_get(url, params=None, timeout=None):
        r = MagicMock()
        call_count[0] += 1
        if call_count[0] == 1:
            r.status_code = 503
            r.headers = {"Retry-After": "2"}
            r.text = ""
        else:
            r.status_code = 200
            r.text = _FAKE_OAI_XML
            r.raise_for_status = MagicMock()
        return r

    with patch("requests.get", side_effect=fake_get):
        with patch("time.sleep"):
            papers = fetch_arxiv_abstracts(category="cs.CV", years=2, limit=100)

    assert len(papers) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 标记：真实模型测试（有网/有模型才跑）
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    True,  # 默认跳过，避免 CI/无网环境拉模型
    reason="需要网络 + SPECTER2 模型权重（allenai/specter2_base），真实环境手动运行"
)
def test_specter2_real_embed():
    """真实 SPECTER2 模型 embed() 测试（需网络 + GPU/CPU）。"""
    from ideation_collision import embed, _try_load_specter2

    assert _try_load_specter2(), "SPECTER2 加载失败"
    vecs = embed(MOCK_CANDIDATES[:2], use_query_adapter=False)
    assert vecs.shape == (2, 768)
    norms = np.linalg.norm(vecs, axis=1)
    np.testing.assert_allclose(norms, np.ones(2), atol=1e-4)


@pytest.mark.skipif(
    True,
    reason="需要网络 + Semantic Scholar API（避免 CI 中真实 HTTP）"
)
def test_fetch_corpus_real():
    """真实 S2 API 拉取测试。"""
    from ideation_collision import fetch_corpus

    papers = fetch_corpus("medical image segmentation", years=1, limit=5)
    assert len(papers) >= 1
    assert "title" in papers[0]


if __name__ == "__main__":
    # 快速冒烟：只跑纯函数测试
    pytest.main([__file__, "-v", "-k", "not real"])
