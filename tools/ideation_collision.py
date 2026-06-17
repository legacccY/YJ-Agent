"""
G1 去重 + G2 撞车检测工具
============================
# deps: pip install transformers adapters faiss-cpu torch requests
#       (adapters 即 adapter-transformers，注意与 transformers 版本兼容)
#
# 用法:
#   python tools/ideation_collision.py --pool runs/<date>_pool.jsonl --corpus <corpus.jsonl>
#   python tools/ideation_collision.py --pool runs/<date>_pool.jsonl --fetch-corpus "medical image segmentation" --corpus-out runs/corpus.jsonl
#   python tools/ideation_collision.py --pool runs/<date>_pool.jsonl --corpus corpus.jsonl --dedup-only
#
# 输出: 就地 append/更新 pool.jsonl 中的 g2_collision 字段 (符合 04_POOL.schema.md)
#
# 降级策略:
#   SPECTER2 加载失败 / 无 GPU → 自动回退 OpenAlex /find/works 轻量 API (无 GPU 需求)
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
import argparse
import pathlib
import re
from typing import Optional

import numpy as np
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ideation_collision")

# ── SPECTER2 相关常量 ────────────────────────────────────────────────────────
_SPECTER2_BASE = "allenai/specter2_base"
_SPECTER2_ADAPTER_PROXIMITY = "allenai/specter2"   # proximity adapter (corpus 端)
_SPECTER2_ADAPTER_QUERY = "allenai/specter2_adhoc_query"  # adhoc_query adapter (候选端)
_EMBED_DIM = 768
_MAX_LENGTH = 512
_BATCH_SIZE = 32   # 8GB 卡 fp32 安全批大小

# ── Semantic Scholar 常量 ───────────────────────────────────────────────────
_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,abstract,year,externalIds"
_S2_MAX_LIMIT = 100   # S2 单页最大
_S2_RETRY_WAIT = 5    # 429 退避秒数

# ── OpenAlex 降级常量 ────────────────────────────────────────────────────────
_OA_FIND_URL = "https://api.openalex.org/find/works"
# TODO: OpenAlex /find/works 为 beta 端点，2026-02 起需免费 key
#       注册 https://openalex.org/register 获取 API key 后用 ?api_key=<key>
#       若无 key 则走匿名 (可能被限速/返空)

# ── 余弦阈值 ────────────────────────────────────────────────────────────────
DEDUP_THRESHOLD = 0.8   # G1 去重：候选间相似 > 此值视为重复
COLLISION_THRESHOLD = 0.85  # G2 撞车：红色警报阈值
COLLISION_WARN = 0.80       # G2 撞车：黄色人工判阈值


# ═══════════════════════════════════════════════════════════════════════════════
# SPECTER2 模型加载（含降级检测）
# ═══════════════════════════════════════════════════════════════════════════════

_specter2_model = None
_specter2_tok = None
_specter2_query_model = None  # 用 adhoc_query adapter
_device = None
_specter2_available = None   # None=未检测, True=可用, False=不可用


def _try_load_specter2() -> bool:
    """
    尝试加载 SPECTER2。成功返回 True，失败返回 False（触发降级）。
    全局单例，多次调用只加载一次。
    """
    global _specter2_model, _specter2_tok, _specter2_query_model, _device, _specter2_available

    if _specter2_available is not None:
        return _specter2_available

    try:
        import torch
        from transformers import AutoTokenizer
        from adapters import AutoAdapterModel

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        if _device == "cpu":
            log.warning("无 GPU 可用，SPECTER2 将用 CPU 推理（速度慢，考虑降级到 OpenAlex）")

        log.info(f"加载 SPECTER2 tokenizer: {_SPECTER2_BASE}")
        _specter2_tok = AutoTokenizer.from_pretrained(_SPECTER2_BASE)

        # proximity model: 用于 corpus 端 embedding（已发论文库）
        log.info("加载 SPECTER2 proximity adapter（corpus 端）")
        _specter2_model = AutoAdapterModel.from_pretrained(_SPECTER2_BASE)
        _specter2_model.load_adapter(
            _SPECTER2_ADAPTER_PROXIMITY,
            source="hf",
            load_as="proximity",
            set_active=True,
        )
        _specter2_model.eval()
        _specter2_model.to(_device)

        # adhoc_query model: 用于候选 idea 端 embedding
        # 官方推荐：query 用 adhoc_query adapter，corpus 用 proximity adapter，混用检索更准
        log.info("加载 SPECTER2 adhoc_query adapter（候选端）")
        _specter2_query_model = AutoAdapterModel.from_pretrained(_SPECTER2_BASE)
        _specter2_query_model.load_adapter(
            _SPECTER2_ADAPTER_QUERY,
            source="hf",
            load_as="adhoc_query",
            set_active=True,
        )
        _specter2_query_model.eval()
        _specter2_query_model.to(_device)

        _specter2_available = True
        log.info(f"SPECTER2 加载成功，device={_device}")
        # TODO: 4070 上确切峰值 VRAM 官方未给，首次跑 nvidia-smi 实测
        return True

    except Exception as e:
        log.warning(f"SPECTER2 加载失败（{e}），将使用 OpenAlex API 降级路径")
        _specter2_available = False
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 核心 embedding 函数
# ═══════════════════════════════════════════════════════════════════════════════

def embed(papers: list[dict], use_query_adapter: bool = False) -> np.ndarray:
    """
    用 SPECTER2 对论文列表计算 embedding。

    Args:
        papers: list of {"title": str, "abstract": str}
        use_query_adapter: True 用 adhoc_query adapter（候选/idea 端）
                           False 用 proximity adapter（corpus/已发论文端）

    Returns:
        np.ndarray shape [N, 768], float32，L2-归一化
    """
    if not _try_load_specter2():
        raise RuntimeError("SPECTER2 不可用，请改用降级路径 collision_openalex()")

    import torch

    model = _specter2_query_model if use_query_adapter else _specter2_model
    tok = _specter2_tok

    def _paper_text(p: dict) -> str:
        # corpus 端为 {title, abstract}；候选端为 {one_liner, problem, approach, why_new}
        if "title" in p:
            return p["title"] + tok.sep_token + (p.get("abstract") or "")
        head = p.get("one_liner") or ""
        body = " ".join(
            p.get(k) or "" for k in ("problem", "approach", "why_new")
        ).strip()
        return head + tok.sep_token + body

    texts = [_paper_text(p) for p in papers]

    all_vecs = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch_texts = texts[i: i + _BATCH_SIZE]
        inp = tok(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=_MAX_LENGTH,
            return_tensors="pt",
        )
        inp = {k: v.to(_device) for k, v in inp.items()}
        with torch.no_grad():
            out = model(**inp)
            cls = out.last_hidden_state[:, 0, :]  # CLS token, [B, 768]
        all_vecs.append(cls.cpu().float().numpy())

    vecs = np.concatenate(all_vecs, axis=0)   # [N, 768]
    # L2 归一化，便于余弦相似度 = 内积
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    vecs = vecs / norms
    return vecs


def _cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    计算余弦相似度矩阵。a[N,D], b[M,D]（均已 L2 归一化）→ [N,M]。
    """
    return a @ b.T


# ═══════════════════════════════════════════════════════════════════════════════
# G1 去重
# ═══════════════════════════════════════════════════════════════════════════════

def dedup(
    candidates: list[dict],
    thr: float = DEDUP_THRESHOLD,
) -> tuple[list[dict], dict[str, str]]:
    """
    G1 候选间余弦去重。

    Args:
        candidates: list of {"id": str, "title": str, "abstract": str, ...}
        thr: 余弦相似度阈值，> thr 视为重复，保留先出现的

    Returns:
        (deduped, merge_map)
        - deduped: 去重后的候选列表
        - merge_map: {被合并的 id -> 保留的 id}
    """
    if len(candidates) == 0:
        return [], {}

    if not _try_load_specter2():
        log.warning("SPECTER2 不可用，dedup 将跳过（返回原始候选）")
        return candidates, {}

    log.info(f"对 {len(candidates)} 个候选计算去重 embedding（query adapter）")
    vecs = embed(candidates, use_query_adapter=True)   # [N, 768]
    sim = _cosine_matrix(vecs, vecs)  # [N, N]

    n = len(candidates)
    merged = set()    # 被合并（删除）的下标
    merge_map = {}    # id -> id

    for i in range(n):
        if i in merged:
            continue
        for j in range(i + 1, n):
            if j in merged:
                continue
            if sim[i, j] > thr:
                cid_i = candidates[i].get("id", str(i))
                cid_j = candidates[j].get("id", str(j))
                log.info(
                    f"  去重：{cid_j} → {cid_i}（cos={sim[i,j]:.3f} > {thr}）"
                )
                merged.add(j)
                merge_map[cid_j] = cid_i

    deduped = [c for idx, c in enumerate(candidates) if idx not in merged]
    log.info(f"去重完成：{len(candidates)} → {len(deduped)}（移除 {len(merged)} 条）")
    return deduped, merge_map


# ═══════════════════════════════════════════════════════════════════════════════
# G2 撞车检测（SPECTER2 + FAISS）
# ═══════════════════════════════════════════════════════════════════════════════

def collision(
    candidates: list[dict],
    corpus: list[dict],
    topk: int = 5,
    thr: float = COLLISION_THRESHOLD,
) -> list[dict]:
    """
    G2 撞车检测：candidates vs corpus，用 SPECTER2 + FAISS inner-product 搜索。

    Args:
        candidates: list of {"id", "title", "abstract"}
        corpus: list of {"title", "abstract"}（已发论文库）
        topk: 每候选返回最近 K 篇
        thr: 红色警报阈值（> thr → g2_kill="撞车"）

    Returns:
        candidates 的副本列表，每条追加 g2_collision 字段（符合 04_POOL.schema.md）
        {
          "max_cos": float,
          "nearest": str,       # 最近论文标题
          "source": "specter2",
          "topk_hits": [{"title":..., "cos":...}],  # 完整 top-K（扩展字段）
        }
    """
    if not _try_load_specter2():
        log.warning("SPECTER2 不可用，回退到 OpenAlex API 降级路径")
        results = []
        for c in candidates:
            g2 = collision_openalex(c)
            item = dict(c)
            item["g2_collision"] = g2
            if g2["max_cos"] > thr:
                item.setdefault("g2_kill", "撞车")
                log.warning(
                    f"  [RED] 候选 {c.get('id','')} 撞车（cos={g2['max_cos']:.3f}）: {g2['nearest']}"
                )
            results.append(item)
        return results

    try:
        import faiss
    except ImportError:
        raise ImportError("请安装 faiss-cpu: pip install faiss-cpu")

    log.info(f"对 corpus {len(corpus)} 篇计算 proximity embedding")
    corpus_vecs = embed(corpus, use_query_adapter=False)  # [M, 768]，proximity adapter

    log.info(f"对 {len(candidates)} 个候选计算 adhoc_query embedding")
    cand_vecs = embed(candidates, use_query_adapter=True)  # [N, 768]

    # 建 FAISS 内积索引（已归一化 → 等价余弦）
    dim = corpus_vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(corpus_vecs.astype(np.float32))

    # 搜索 top-K
    scores, indices = index.search(cand_vecs.astype(np.float32), topk)
    # scores[i, k] = 余弦相似度（内积，已归一化）

    results = []
    for i, cand in enumerate(candidates):
        max_cos = float(scores[i, 0]) if len(scores[i]) > 0 else 0.0
        nearest_idx = int(indices[i, 0]) if len(indices[i]) > 0 else -1
        nearest_title = corpus[nearest_idx]["title"] if nearest_idx >= 0 else ""

        topk_hits = []
        for k in range(len(scores[i])):
            idx_k = int(indices[i, k])
            if idx_k < 0:
                continue
            topk_hits.append({
                "title": corpus[idx_k]["title"],
                "cos": round(float(scores[i, k]), 4),
            })

        g2 = {
            "max_cos": round(max_cos, 4),
            "nearest": nearest_title,
            "source": "specter2",
            "topk_hits": topk_hits,
        }

        item = dict(cand)
        item["g2_collision"] = g2

        if max_cos > thr:
            item.setdefault("g2_kill", "撞车")
            log.warning(
                f"  [RED] 候选 {cand.get('id','')} 撞车（cos={max_cos:.3f} > {thr}）: {nearest_title}"
            )
        elif max_cos > COLLISION_WARN:
            log.warning(
                f"  [YEL] 候选 {cand.get('id','')} 疑似（cos={max_cos:.3f}，人工判）: {nearest_title}"
            )
        else:
            log.info(
                f"  [OK]  候选 {cand.get('id','')} 安全（max_cos={max_cos:.3f}）"
            )

        results.append(item)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 降级路径：OpenAlex /find/works
# ═══════════════════════════════════════════════════════════════════════════════

def collision_openalex(
    candidate: dict,
    topk: int = 5,
    openalex_api_key: Optional[str] = None,
) -> dict:
    """
    轻量降级：用 OpenAlex /find/works 语义搜索（beta），不需 GPU。
    返回 g2_collision schema dict（source="openalex"）。

    NOTE: OpenAlex /find/works 是 beta 端点，无标准文档保证稳定性。
    TODO: 2026-02 起需免费 key（注册 https://openalex.org/register），
          无 key 匿名可能被限速或返回空结果。
    """
    abstract = (candidate.get("abstract") or "")[:2000]  # 截断避免 URL 过长
    title = candidate.get("title", "")
    query_text = f"{title}. {abstract}".strip()

    params: dict = {
        "filter": f"abstract.search:{requests.utils.quote(title)}",
        "per-page": topk,
        "select": "title,id,doi",
    }
    # /find/works 是语义端点，传 full text 查询
    # TODO: 端点行为未完全核实，以实测为准
    find_params: dict = {"abstract": query_text[:1000]}
    if openalex_api_key:
        find_params["api_key"] = openalex_api_key
    else:
        # 无 key 加 mailto 走 polite pool（提高配额）
        find_params["mailto"] = "legacccy1@gmail.com"

    try:
        resp = requests.get(
            _OA_FIND_URL,
            params=find_params,
            timeout=15,
        )
        if resp.status_code == 404:
            # /find/works 可能未对匿名开放
            log.warning("OpenAlex /find/works 返回 404，端点可能需 key 或 beta 已变更")
            return {"max_cos": 0.0, "nearest": "", "source": "openalex", "error": "404"}
        resp.raise_for_status()
        data = resp.json()

        results_raw = data.get("results", [])
        if not results_raw:
            return {"max_cos": 0.0, "nearest": "", "source": "openalex"}

        # OpenAlex /find/works 按相关度排序，第一条 = 最相近
        # 无直接余弦分数，用 rank 归一估算（降级路径仅供快速初筛）
        nearest_title = results_raw[0].get("title", "")
        # 降级路径无真实余弦，填保守估算（0.7 表示"有相关结果，需人工判断"）
        # TODO: 若 OpenAlex 返回相似度分数则替换此估算
        est_cos = 0.70 if results_raw else 0.0

        return {
            "max_cos": est_cos,
            "nearest": nearest_title,
            "source": "openalex",
            "note": "降级路径：余弦为估算值（非真实 embedding 相似度），仅供初筛",
        }

    except requests.exceptions.Timeout:
        log.warning(f"OpenAlex 请求超时（候选：{title[:50]}）")
        return {"max_cos": 0.0, "nearest": "", "source": "openalex", "error": "timeout"}
    except Exception as e:
        log.warning(f"OpenAlex 请求失败（{e}）")
        return {"max_cos": 0.0, "nearest": "", "source": "openalex", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# 语料拉取：Semantic Scholar 批量搜索
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_corpus(
    keyword: str,
    years: int = 3,
    limit: int = 2000,
    s2_api_key: Optional[str] = None,
    output_path: Optional[str] = None,
) -> list[dict]:
    """
    从 Semantic Scholar 拉取 keyword 近 N 年论文作为撞车检测语料库。

    Args:
        keyword: 搜索关键词（如 "medical image segmentation"）
        years: 近几年（从当前年往回算）
        limit: 最多拉取篇数（S2 免费额度内，建议 500-2000）
        s2_api_key: 可选，S2 API key（无 key 走共享池，有 key 1 req/s）
        output_path: 可选，保存路径（jsonl）

    Returns:
        list of {"title": str, "abstract": str, "year": int, "paperId": str}
    """
    import datetime
    current_year = datetime.datetime.now().year
    year_filter = f"{current_year - years}-{current_year}"

    headers = {}
    if s2_api_key:
        headers["x-api-key"] = s2_api_key

    papers = []
    offset = 0
    page_size = min(_S2_MAX_LIMIT, 100)

    log.info(f"从 S2 拉取语料：keyword='{keyword}', years={year_filter}, limit={limit}")

    while len(papers) < limit:
        remaining = limit - len(papers)
        current_limit = min(page_size, remaining)

        params = {
            "query": keyword,
            "fields": _S2_FIELDS,
            "limit": current_limit,
            "offset": offset,
            "year": year_filter,
        }

        retry = 0
        max_retry = 5
        while retry < max_retry:
            try:
                resp = requests.get(
                    _S2_SEARCH_URL,
                    params=params,
                    headers=headers,
                    timeout=20,
                )
                if resp.status_code == 429:
                    wait = _S2_RETRY_WAIT * (2 ** retry)
                    log.warning(f"S2 限速 429，等待 {wait}s 后重试（{retry+1}/{max_retry}）")
                    time.sleep(wait)
                    retry += 1
                    continue
                resp.raise_for_status()
                break
            except requests.exceptions.Timeout:
                wait = _S2_RETRY_WAIT * (2 ** retry)
                log.warning(f"S2 超时，等待 {wait}s 后重试")
                time.sleep(wait)
                retry += 1

        if retry >= max_retry:
            log.error(f"S2 请求连续失败 {max_retry} 次，停止拉取")
            break

        data = resp.json()
        batch = data.get("data", [])
        if not batch:
            log.info("S2 返回空，已到末页")
            break

        for p in batch:
            papers.append({
                "title": p.get("title", ""),
                "abstract": p.get("abstract") or "",
                "year": p.get("year"),
                "paperId": p.get("paperId", ""),
                "source": "s2",
            })

        offset += len(batch)
        log.info(f"  已拉取 {len(papers)} 篇（本批 {len(batch)}）")

        # S2 无 key 时礼貌等待
        if not s2_api_key:
            time.sleep(1.0)

        if len(batch) < current_limit:
            log.info("S2 返回不足一页，已到末页")
            break

    log.info(f"语料拉取完成：共 {len(papers)} 篇")

    if output_path:
        out = pathlib.Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for p in papers:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        log.info(f"语料已保存：{output_path}")

    return papers


# ═══════════════════════════════════════════════════════════════════════════════
# Pool JSONL 读写工具
# ═══════════════════════════════════════════════════════════════════════════════

def load_jsonl(path: str) -> list[dict]:
    """读取 JSONL 文件，每行一个 JSON 对象。"""
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                log.warning(f"第 {lineno} 行 JSON 解析失败（跳过）：{e}")
    return items


def save_jsonl(items: list[dict], path: str) -> None:
    """写回 JSONL 文件（覆盖），保持 append-only 语义（不删行）。"""
    out = pathlib.Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    log.info(f"已写回 {len(items)} 条到 {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_args():
    parser = argparse.ArgumentParser(
        description="G1 去重 + G2 撞车检测工具 (ideation_collision.py)"
    )
    parser.add_argument("--pool", required=True, help="候选池 JSONL 路径（04_POOL.schema.md 格式）")
    parser.add_argument(
        "--corpus",
        default=None,
        help="已发论文语料库 JSONL 路径（含 title/abstract 字段）",
    )
    parser.add_argument(
        "--fetch-corpus",
        default=None,
        metavar="KEYWORD",
        help="从 Semantic Scholar 拉取语料库（传关键词，配合 --corpus-out）",
    )
    parser.add_argument("--corpus-out", default=None, help="拉取语料保存路径")
    parser.add_argument(
        "--years", type=int, default=3, help="语料年份范围（默认近 3 年）"
    )
    parser.add_argument(
        "--corpus-limit", type=int, default=2000, help="语料最大篇数（默认 2000）"
    )
    parser.add_argument(
        "--dedup-only",
        action="store_true",
        help="仅做 G1 候选间去重，跳过 G2 撞车检测",
    )
    parser.add_argument(
        "--topk", type=int, default=5, help="G2 撞车检测 top-K（默认 5）"
    )
    parser.add_argument(
        "--dedup-thr", type=float, default=DEDUP_THRESHOLD, help=f"G1 去重阈值（默认 {DEDUP_THRESHOLD}）"
    )
    parser.add_argument(
        "--collision-thr", type=float, default=COLLISION_THRESHOLD,
        help=f"G2 红色警报阈值（默认 {COLLISION_THRESHOLD}）"
    )
    parser.add_argument("--s2-key", default=None, help="Semantic Scholar API key（可选）")
    parser.add_argument("--oa-key", default=None, help="OpenAlex API key（可选，beta 端点）")
    return parser.parse_args()


def main():
    args = _parse_args()

    # 1. 加载候选池
    log.info(f"加载候选池：{args.pool}")
    candidates = load_jsonl(args.pool)
    log.info(f"  候选数：{len(candidates)}")

    # 2. 可选：拉取语料
    corpus = []
    if args.fetch_corpus:
        corpus_path = args.corpus_out or args.corpus
        corpus = fetch_corpus(
            keyword=args.fetch_corpus,
            years=args.years,
            limit=args.corpus_limit,
            s2_api_key=args.s2_key,
            output_path=corpus_path,
        )
    elif args.corpus:
        log.info(f"加载语料库：{args.corpus}")
        corpus = load_jsonl(args.corpus)
        log.info(f"  语料篇数：{len(corpus)}")

    # 3. G1 去重
    deduped, merge_map = dedup(candidates, thr=args.dedup_thr)

    # 标记被合并的候选
    id_to_item = {c.get("id", str(i)): c for i, c in enumerate(candidates)}
    for merged_id, kept_id in merge_map.items():
        if merged_id in id_to_item:
            id_to_item[merged_id]["status"] = "killed@G1"
            id_to_item[merged_id]["kill_reason"] = f"去重：合并到 {kept_id}"

    if args.dedup_only or not corpus:
        if not corpus and not args.dedup_only:
            log.warning("未提供语料库（--corpus / --fetch-corpus），跳过 G2 撞车检测")
        save_jsonl(candidates, args.pool)
        log.info("完成（仅去重）")
        return

    # 4. G2 撞车检测（仅对存活候选）
    alive = [c for c in deduped if c.get("status") != "killed@G1"]
    log.info(f"G2 撞车检测：{len(alive)} 个存活候选 vs {len(corpus)} 篇语料")

    results = collision(alive, corpus, topk=args.topk, thr=args.collision_thr)

    # 将结果合并回原始候选池（按 id 匹配）
    result_map = {r.get("id", ""): r for r in results}
    for item in candidates:
        cid = item.get("id", "")
        if cid in result_map:
            r = result_map[cid]
            item["g2_collision"] = r.get("g2_collision")
            if "g2_kill" in r:
                item["g2_kill"] = r["g2_kill"]
                item["status"] = "killed@G2"
                item["kill_reason"] = "G2 撞车检测：cos > 阈值"

    save_jsonl(candidates, args.pool)
    log.info("完成（G1 去重 + G2 撞车检测，结果已写回 pool）")


if __name__ == "__main__":
    main()
