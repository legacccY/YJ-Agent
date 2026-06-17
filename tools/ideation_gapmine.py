"""
S1 gap 挖掘工具（future-work / limitation 句聚类）
=======================================================
# deps: pip install requests numpy scikit-learn
#       可选（主路径）: pip install bertopic sentence-transformers
#       可选（SPECTER2）: pip install transformers adapters torch
#
# 用法:
#   python tools/ideation_gapmine.py --category cs.CV --years 2 --out runs/2026-06-17_gaps.jsonl
#   python tools/ideation_gapmine.py --category cs.LG --years 1 --limit 500 --kmeans-k 20
#
# 流程:
#   1. arXiv OAI-PMH 按 category 拉近 N 年元数据 + abstract
#   2. regex 抽 future-work / limitation 相关句
#   3a. (主路径) BERTopic 聚类 → gap cluster
#   3b. (降级) SPECTER2 / sentence-transformers embedding + sklearn KMeans
#   3c. (轻量降级) 纯 TF-IDF KMeans（无深度模型依赖）
#   4. 输出 runs/<date>_gaps.jsonl，每行一个 gap cluster
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
import xml.etree.ElementTree as ET
from typing import Optional, Iterator
from datetime import datetime, timezone

import numpy as np
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ideation_gapmine")

# ── arXiv OAI-PMH 常量 ───────────────────────────────────────────────────────
_ARXIV_OAI_URL = "http://export.arxiv.org/oai2"
_ARXIV_RATE_LIMIT = 3.0   # 1 req / 3s 礼貌限速
_OAI_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "arxiv": "http://arxiv.org/OAI/arXiv/",
}

# ── Future-work / limitation 句模式 ─────────────────────────────────────────
_FW_PATTERNS = [
    r"future work",
    r"future research",
    r"future studi",
    r"we plan to",
    r"one limitation",
    r"a limitation",
    r"limitations? of (this|our)",
    r"left for future",
    r"promising direction",
    r"remain(s)? (an? )?(open|challenge|unsolved)",
    r"not (yet )?(addressed|explored|investigated)",
    r"beyond the scope",
    r"could be extend",
    r"we leave",
    r"promising avenue",
    r"open problem",
    r"open question",
    r"remain(s)? unclear",
    r"challenging (and )?remain",
    r"yet to be",
    r"needs? (further|more) (investigation|exploration|study|work)",
]
_FW_REGEX = re.compile(
    "|".join(_FW_PATTERNS),
    re.IGNORECASE,
)

# 句子分割（简单分割，避免 nltk 依赖）
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


# ═══════════════════════════════════════════════════════════════════════════════
# arXiv OAI-PMH 拉取
# ═══════════════════════════════════════════════════════════════════════════════

def _oai_request(params: dict, max_retry: int = 5) -> Optional[ET.Element]:
    """发送 OAI-PMH 请求，带退避重试。返回 XML 根节点或 None。"""
    for attempt in range(max_retry):
        try:
            resp = requests.get(_ARXIV_OAI_URL, params=params, timeout=30)
            if resp.status_code == 503:
                # arXiv 流控：响应体包含 Retry-After
                retry_after = int(resp.headers.get("Retry-After", 20))
                log.warning(f"arXiv 503，等待 {retry_after}s（尝试 {attempt+1}/{max_retry}）")
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            return root
        except requests.exceptions.Timeout:
            wait = 10 * (2 ** attempt)
            log.warning(f"arXiv 超时，等待 {wait}s 后重试")
            time.sleep(wait)
        except Exception as e:
            log.error(f"arXiv OAI 请求失败：{e}")
            return None
    return None


def fetch_arxiv_abstracts(
    category: str = "cs.CV",
    years: int = 2,
    limit: int = 3000,
) -> list[dict]:
    """
    通过 arXiv OAI-PMH 批量拉取 category 近 N 年的论文元数据 + abstract。

    Args:
        category: arXiv category（如 cs.CV / cs.LG / q-bio.QM）
        years: 拉取近几年（从当前年往回）
        limit: 最多拉取篇数（OAI-PMH 每页 1000 条）

    Returns:
        list of {"arxiv_id", "title", "abstract", "categories", "year"}
    """
    from datetime import date, timedelta

    today = date.today()
    from_date = (today.replace(year=today.year - years)).strftime("%Y-%m-%d")
    until_date = today.strftime("%Y-%m-%d")

    params = {
        "verb": "ListRecords",
        "set": category,
        "metadataPrefix": "arXiv",
        "from": from_date,
        "until": until_date,
    }

    papers = []
    log.info(f"arXiv OAI-PMH 拉取：category={category}, from={from_date}, until={until_date}, limit={limit}")

    while True:
        root = _oai_request(params)
        if root is None:
            log.error("OAI-PMH 请求失败，停止")
            break

        # 解析 records
        list_records = root.find("oai:ListRecords", _OAI_NS)
        if list_records is None:
            # 检查是否有错误
            error_el = root.find("oai:error", _OAI_NS)
            if error_el is not None:
                log.error(f"OAI-PMH 错误：{error_el.get('code')} - {error_el.text}")
            break

        for record in list_records.findall("oai:record", _OAI_NS):
            meta = record.find("oai:metadata", _OAI_NS)
            if meta is None:
                continue
            arxiv_el = meta.find("arxiv:arXiv", _OAI_NS)
            if arxiv_el is None:
                continue

            arxiv_id = (arxiv_el.findtext("arxiv:id", "", _OAI_NS) or "").strip()
            title_raw = arxiv_el.findtext("arxiv:title", "", _OAI_NS) or ""
            abstract_raw = arxiv_el.findtext("arxiv:abstract", "", _OAI_NS) or ""
            cats = arxiv_el.findtext("arxiv:categories", "", _OAI_NS) or ""

            # 清理空白
            title = re.sub(r"\s+", " ", title_raw).strip()
            abstract = re.sub(r"\s+", " ", abstract_raw).strip()

            if not title or not abstract:
                continue

            # 提取年份（arxiv_id 格式：YYMM.NNNNN 或旧格式）
            year_match = re.match(r"^(\d{2})(\d{2})\.", arxiv_id)
            if year_match:
                yy = int(year_match.group(1))
                year = 2000 + yy if yy < 50 else 1900 + yy
            else:
                year = None

            papers.append({
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "categories": cats,
                "year": year,
            })

            if len(papers) >= limit:
                log.info(f"已达上限 {limit} 篇，停止")
                return papers

        # resumptionToken
        token_el = list_records.find("oai:resumptionToken", _OAI_NS)
        if token_el is None or not (token_el.text or "").strip():
            log.info("OAI-PMH 无 resumptionToken，已到末页")
            break

        token = token_el.text.strip()
        log.info(f"  已拉取 {len(papers)} 篇，继续翻页（token={token[:20]}...）")
        params = {"verb": "ListRecords", "resumptionToken": token}

        # 礼貌限速
        time.sleep(_ARXIV_RATE_LIMIT)

    log.info(f"arXiv 拉取完成：共 {len(papers)} 篇")
    return papers


# ═══════════════════════════════════════════════════════════════════════════════
# Future-work 句抽取
# ═══════════════════════════════════════════════════════════════════════════════

def extract_fw_sentences(papers: list[dict]) -> list[dict]:
    """
    从 abstract 中抽取 future-work / limitation 相关句。

    NOTE: 理想情况下应用 grobid / AllenAI Science Parse 抽 full-text section，
    但 abstract 已包含作者对 future-work 的简要陈述，是可用的轻量替代。
    TODO: 接入 grobid 提升召回率（需 Docker 环境）。

    Returns:
        list of {
            "arxiv_id", "title", "year", "sentence",
            "source_paper": {"title": ..., "arxiv_id": ...}
        }
    """
    fw_sents = []
    for paper in papers:
        abstract = paper.get("abstract", "")
        if not abstract:
            continue

        # 句子分割
        sents = _SENT_SPLIT.split(abstract)

        for sent in sents:
            sent = sent.strip()
            if len(sent) < 20:  # 过滤过短句
                continue
            if _FW_REGEX.search(sent):
                fw_sents.append({
                    "arxiv_id": paper.get("arxiv_id", ""),
                    "title": paper.get("title", ""),
                    "year": paper.get("year"),
                    "sentence": sent,
                    "source_paper": {
                        "title": paper.get("title", ""),
                        "arxiv_id": paper.get("arxiv_id", ""),
                    },
                })

    log.info(f"future-work 句抽取：{len(papers)} 篇 → {len(fw_sents)} 条句子")
    return fw_sents


# ═══════════════════════════════════════════════════════════════════════════════
# 聚类路径选择（BERTopic 主路径 → SPECTER2/SentTrans 降级 → TF-IDF 轻量降级）
# ═══════════════════════════════════════════════════════════════════════════════

def _try_bertopic_cluster(sentences: list[str], n_topics: int = 30) -> Optional[list[int]]:
    """尝试 BERTopic 聚类，失败返回 None。"""
    try:
        from bertopic import BERTopic

        log.info("使用 BERTopic 聚类（主路径）")
        topic_model = BERTopic(
            nr_topics=n_topics,
            min_topic_size=3,
            verbose=False,
        )
        topics, _ = topic_model.fit_transform(sentences)
        log.info(f"BERTopic 聚类完成：{len(set(t for t in topics if t != -1))} 个 topic（-1=噪声）")
        return topics
    except ImportError:
        log.warning("BERTopic 未安装（pip install bertopic）")
        return None
    except Exception as e:
        log.warning(f"BERTopic 失败（{e}），将降级")
        return None


def _try_specter2_kmeans(
    sentences: list[str],
    k: int = 20,
) -> Optional[list[int]]:
    """
    SPECTER2 / sentence-transformers embedding + KMeans 降级聚类。
    先尝试 sentence-transformers（all-MiniLM-L6-v2，轻量），
    再尝试 SPECTER2（更准但重），
    失败返回 None。
    """
    vecs = None

    # 优先尝试 sentence-transformers（更轻）
    try:
        from sentence_transformers import SentenceTransformer
        log.info("使用 sentence-transformers 降级聚类（all-MiniLM-L6-v2）")
        st_model = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = st_model.encode(sentences, show_progress_bar=True, batch_size=64)
        log.info(f"sentence-transformers embedding 完成，shape={vecs.shape}")
    except ImportError:
        log.warning("sentence-transformers 未安装（pip install sentence-transformers）")
    except Exception as e:
        log.warning(f"sentence-transformers 失败（{e}）")

    # 若失败，尝试从 ideation_collision 复用 SPECTER2
    if vecs is None:
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).parent))
            from ideation_collision import embed as specter2_embed, _try_load_specter2

            if _try_load_specter2():
                log.info("使用 SPECTER2 降级聚类（proxy：包装句子为 paper dict）")
                paper_dicts = [{"title": s, "abstract": ""} for s in sentences]
                vecs = specter2_embed(paper_dicts, use_query_adapter=True)
                log.info(f"SPECTER2 embedding 完成，shape={vecs.shape}")
        except Exception as e:
            log.warning(f"SPECTER2 失败（{e}）")

    if vecs is None:
        return None

    # KMeans 聚类
    from sklearn.cluster import KMeans

    effective_k = min(k, len(sentences) // 3, len(sentences))
    if effective_k < 2:
        log.warning("句子数过少，无法聚类")
        return [0] * len(sentences)

    log.info(f"KMeans 聚类：k={effective_k}")
    km = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
    labels = km.fit_predict(vecs)
    log.info(f"KMeans 聚类完成：{effective_k} 簇")
    return labels.tolist()


def _tfidf_kmeans_fallback(sentences: list[str], k: int = 20) -> list[int]:
    """
    最轻量降级：TF-IDF + KMeans（无深度模型依赖）。
    质量最低但不依赖任何 GPU 或大模型。
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans

    log.info("使用 TF-IDF + KMeans 轻量降级聚类")
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    X = vectorizer.fit_transform(sentences)

    effective_k = min(k, len(sentences) // 3, len(sentences))
    if effective_k < 2:
        return [0] * len(sentences)

    km = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    log.info(f"TF-IDF KMeans 完成：{effective_k} 簇（轻量降级，质量较低）")
    return labels.tolist()


def cluster_sentences(
    fw_items: list[dict],
    k: int = 20,
    method: str = "auto",
) -> list[dict]:
    """
    对 future-work 句进行聚类，返回簇列表。

    Args:
        fw_items: extract_fw_sentences 的输出
        k: 目标簇数（BERTopic 会自动调整）
        method: "auto" | "bertopic" | "embedding_kmeans" | "tfidf"

    Returns:
        list of {
            "cluster_id": int,
            "size": int,
            "representative_sentences": [str],  # 最多 5 条代表句
            "source_papers": [{"title", "arxiv_id"}],
            "gap_summary": str,   # 代表句拼接（供后续 LLM 汇总，当前为原句）
            "cluster_method": str,
        }
    """
    if not fw_items:
        log.warning("无 future-work 句可聚类")
        return []

    sentences = [item["sentence"] for item in fw_items]
    log.info(f"聚类 {len(sentences)} 条 future-work 句（method={method}, k={k}）")

    labels = None
    cluster_method = ""

    if method in ("auto", "bertopic"):
        labels = _try_bertopic_cluster(sentences, n_topics=k)
        if labels is not None:
            cluster_method = "bertopic"

    if labels is None and method in ("auto", "embedding_kmeans"):
        labels = _try_specter2_kmeans(sentences, k=k)
        if labels is not None:
            cluster_method = "embedding_kmeans"

    if labels is None:
        labels = _tfidf_kmeans_fallback(sentences, k=k)
        cluster_method = "tfidf_kmeans"

    # 组织簇
    from collections import defaultdict
    cluster_map: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        cluster_map[label].append(idx)

    clusters = []
    for cid, indices in sorted(cluster_map.items()):
        if cid == -1:
            # BERTopic 噪声簇，跳过
            continue

        sents_in_cluster = [fw_items[i]["sentence"] for i in indices]
        papers_in_cluster = [fw_items[i]["source_paper"] for i in indices]

        # 去重论文
        seen_ids = set()
        unique_papers = []
        for p in papers_in_cluster:
            pid = p.get("arxiv_id", p.get("title", ""))
            if pid not in seen_ids:
                seen_ids.add(pid)
                unique_papers.append(p)

        # 代表句（最多 5 条，按长度选较长的）
        sorted_sents = sorted(sents_in_cluster, key=len, reverse=True)
        rep_sents = sorted_sents[:5]

        clusters.append({
            "cluster_id": int(cid),
            "size": len(indices),
            "representative_sentences": rep_sents,
            "source_papers": unique_papers[:20],  # 最多 20 篇来源
            "gap_summary": " | ".join(rep_sents[:3]),
            "cluster_method": cluster_method,
        })

    # 按 size 降序
    clusters.sort(key=lambda x: x["size"], reverse=True)
    log.info(f"聚类完成：{len(clusters)} 个 gap cluster（方法: {cluster_method}）")
    return clusters


# ═══════════════════════════════════════════════════════════════════════════════
# 输出格式化为 ideation pool 用的 gap JSONL
# ═══════════════════════════════════════════════════════════════════════════════

def format_gap_output(
    clusters: list[dict],
    category: str,
    years: int,
    total_papers: int,
    total_fw_sents: int,
) -> list[dict]:
    """
    将 gap cluster 格式化为候选池条目，供 G1 ideator 使用。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    gap_items = []

    for i, cluster in enumerate(clusters):
        item = {
            "id": f"GAP-{i+1:03d}",
            "gen_date": today,
            "strategy": "S1-gap",
            "source_category": category,
            "source_years": years,
            "cluster_id": cluster["cluster_id"],
            "cluster_size": cluster["size"],
            "cluster_method": cluster["cluster_method"],
            "representative_sentences": cluster["representative_sentences"],
            "source_papers": cluster["source_papers"],
            "gap_summary": cluster["gap_summary"],
            # 以下字段留空，供人工/G1 ideator 填充
            "one_liner": None,
            "problem": None,
            "approach": None,
            "why_new": None,
            "venue_top": None,
            "venue_fallback": None,
            "datasets": [],
            "compute_est": None,
            "status": "alive",
            # 元信息
            "_meta": {
                "total_papers_scanned": total_papers,
                "total_fw_sentences": total_fw_sents,
            },
        }
        gap_items.append(item)

    return gap_items


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_args():
    parser = argparse.ArgumentParser(
        description="S1 gap 挖掘工具 (ideation_gapmine.py)"
    )
    parser.add_argument(
        "--category",
        default="cs.CV",
        help="arXiv category（默认 cs.CV；支持多个用逗号分隔，如 cs.CV,cs.LG）",
    )
    parser.add_argument("--years", type=int, default=2, help="近几年（默认 2 年）")
    parser.add_argument(
        "--limit", type=int, default=3000, help="最多拉取篇数（默认 3000）"
    )
    parser.add_argument(
        "--kmeans-k", type=int, default=30, help="聚类簇数（默认 30）"
    )
    parser.add_argument(
        "--method",
        choices=["auto", "bertopic", "embedding_kmeans", "tfidf"],
        default="auto",
        help="聚类方法（默认 auto：BERTopic → embedding+KMeans → TF-IDF）",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="输出路径（默认 runs/<YYYY-MM-DD>_gaps.jsonl）",
    )
    parser.add_argument(
        "--arxiv-cache",
        default=None,
        help="arXiv 原始数据缓存路径（避免重复拉取，可选）",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    today_str = datetime.now().strftime("%Y-%m-%d")
    out_path = args.out or f"runs/{today_str}_gaps.jsonl"
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    categories = [c.strip() for c in args.category.split(",") if c.strip()]
    all_papers = []

    for cat in categories:
        # 检查缓存
        cache_path = None
        if args.arxiv_cache:
            cache_path = pathlib.Path(args.arxiv_cache) / f"{cat.replace('.', '_')}_{args.years}y.jsonl"
            if cache_path.exists():
                log.info(f"使用缓存：{cache_path}")
                with open(cache_path, "r", encoding="utf-8") as f:
                    papers = [json.loads(l) for l in f if l.strip()]
                all_papers.extend(papers)
                continue

        papers = fetch_arxiv_abstracts(
            category=cat,
            years=args.years,
            limit=args.limit,
        )
        all_papers.extend(papers)

        if args.arxiv_cache and cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                for p in papers:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")
            log.info(f"已缓存 arXiv 数据：{cache_path}")

    log.info(f"共拉取 {len(all_papers)} 篇论文（categories: {categories}）")

    # 抽取 future-work 句
    fw_items = extract_fw_sentences(all_papers)

    if not fw_items:
        log.warning("未抽取到任何 future-work 句，检查 category / 年份是否正确")
        return

    # 聚类
    clusters = cluster_sentences(fw_items, k=args.kmeans_k, method=args.method)

    # 格式化输出
    gap_items = format_gap_output(
        clusters=clusters,
        category=args.category,
        years=args.years,
        total_papers=len(all_papers),
        total_fw_sents=len(fw_items),
    )

    # 写出
    with open(out_path, "w", encoding="utf-8") as f:
        for item in gap_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    log.info(f"gap 挖掘完成：{len(gap_items)} 个 cluster 写入 {out_path}")
    print(f"\n[OK] {len(gap_items)} gaps → {out_path}")
    print(f"      扫描 {len(all_papers)} 篇论文，抽取 {len(fw_items)} 条 future-work 句")
    print(f"      聚类方法: {clusters[0]['cluster_method'] if clusters else 'N/A'}")


if __name__ == "__main__":
    main()
