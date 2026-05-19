"""Fig 1 teaser 候选池生成器。

按三重打分从 ITB-LQ 池筛每种降质（Blur / Contrast / Colour）各 8 张候选 +
从 ITB-HQ 池筛 8 张 well-calibrated HQ 参考，输出 4 个拼接 PNG 让用户手选最终样本。

打分规则（每个降质池）：
  1. 主降质维度极低（如 Blur 池要求 sharpness < 第 15 百分位）
  2. benign 标签（target = 0）
  3. Std VIB 严重过置信（prob_pos > 0.85）
  4. QCTS 修正幅度大（Δprob > 0.05）
  5. score = -prob_qcts + 0.5*(prob_vib - prob_qcts)  排序取 top

HQ Reference 池：
  1. qbar > 0.60
  2. benign
  3. Std VIB prob_pos < 0.20（well-calibrated benign）

Usage:
  cd D:/YJ-Agent
  python project/scripts/select_teaser_candidates.py

Output:
  project/meeting/BMVC/figures/teaser_candidates/
    pool_hq.png      # 8 张 HQ 候选拼接
    pool_blur.png    # 8 张 Blur 候选拼接
    pool_contrast.png
    pool_colour.png
    candidates.csv   # 全部候选 metadata（最终选定后人工填 selected=True）
"""

from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = Path("D:/YJ-Agent")
DATA = ROOT / "data"
RES  = ROOT / "project/results"
OUT  = ROOT / "project/meeting/BMVC/figures/teaser_candidates"
OUT.mkdir(parents=True, exist_ok=True)

RAW = DATA / "raw/isic2020/train-image/image"
DEG = DATA / "paired_dataset/heavy"

THUMB    = 300     # 单图缩略尺寸
GAP      = 12      # 拼接间距
META_H   = 110     # 图下方 metadata 区域高度（要放 5 维 quality + Std/QCTS/Δ）
COLS     = 4       # 每行 4 张
N_LQ     = 16      # ITB-LQ 过置信总池 top 16
N_HQ     = 8       # HQ 参考池

DIM_PRETTY = {
    "sharpness":    "Blur q_1",
    "brightness":   "Brightness q_2",
    "completeness": "Completeness q_3",
    "color_temp":   "Colour q_4",
    "contrast":     "Contrast q_5",
}


def load_aligned():
    """Load ITB subsets + Std VIB pred + QCTS pred + quality scores, aligned by row."""
    sub  = pd.read_csv(RES / "itb_subsets.csv")
    pred = pd.read_csv(RES / "itb_predictions.csv")
    qcts = pd.read_csv(RES / "qcts_itb_predictions.csv")
    qual = pd.read_csv(DATA / "quality_labels_all.csv")

    # Std VIB on ITB-LQ
    out = {}
    for subset in ["ITB-LQ", "ITB-HQ"]:
        s   = sub [sub.subset  == subset].reset_index(drop=True)
        pd_ = pred[(pred.subset == subset) & (pred.baseline == "D")].reset_index(drop=True)
        qc_ = qcts[(qcts.subset == subset) & (qcts.baseline == "D+QCTS")].reset_index(drop=True)
        assert len(s) == len(pd_) == len(qc_), f"{subset} row mismatch"
        # qbar 一致性检查
        if not np.allclose(s["qbar"].values, pd_["qbar"].values):
            raise RuntimeError(f"{subset} qbar misalign")
        m = s.copy()
        m["prob_vib"]  = pd_["prob_pos"].values
        m["prob_qcts"] = qc_["prob_pos"].values
        m["delta"]     = m["prob_vib"] - m["prob_qcts"]
        # 合并 5 维 quality scores（用 degraded_path = image_path）
        qual_norm = qual.copy()
        qual_norm["degraded_path"] = qual_norm["degraded_path"].str.replace("\\", "/", regex=False)
        m["image_path_norm"] = m["image_path"].str.replace("\\", "/", regex=False)
        m = m.merge(
            qual_norm[["degraded_path", "sharpness", "brightness", "completeness", "color_temp", "contrast"]],
            left_on="image_path_norm", right_on="degraded_path", how="left",
        )
        out[subset] = m
    return out


DIM_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]


def pick_lq_pool(df_lq: pd.DataFrame, n: int = N_LQ) -> pd.DataFrame:
    """从 ITB-LQ 筛 benign + Std VIB 过置信的总池，按主降质维度自动标注。"""
    cand = df_lq[
        (df_lq["target"] == 0)
        & (df_lq["prob_vib"] > 0.50)   # 放宽到 0.5
    ].copy()
    if len(cand) == 0:
        return cand

    # 标注主降质维度 = 5 维 quality scores 中最低的那个
    qual_mat = cand[DIM_COLS].values
    primary_idx = qual_mat.argmin(axis=1)
    cand["primary_dim"]    = [DIM_COLS[i] for i in primary_idx]
    cand["primary_value"]  = qual_mat[np.arange(len(cand)), primary_idx]

    # 排序：先按主降质极端度（值越低越好），再按 prob_vib 高、delta 大
    cand["score"] = -cand["primary_value"] + 0.5 * cand["prob_vib"] + 0.3 * cand["delta"]
    cand = cand.sort_values("score", ascending=False).head(n)
    cand["pool"] = "lq_overconf"
    return cand


def pick_hq_pool(df_hq: pd.DataFrame, n: int = N_HQ) -> pd.DataFrame:
    """从 ITB-HQ 筛 well-calibrated benign 参考。"""
    cand = df_hq[
        (df_hq["qbar"]     > 0.55)
        & (df_hq["target"] == 0)
        & (df_hq["prob_vib"] < 0.25)
    ].copy()
    # 排序：qbar 高 + prob 低 = 最好的参考
    cand["score"] = cand["qbar"] - 0.5 * cand["prob_vib"]
    cand = cand.sort_values("score", ascending=False).head(n)
    cand["pool"]        = "hq"
    cand["primary_dim"] = ""
    cand["primary_value"] = np.nan
    return cand


def load_thumb(isic_id: str, use_deg: bool) -> Image.Image:
    """加载缩略图：HQ 用 raw，降质用 paired_dataset/heavy。"""
    path = (DEG if use_deg else RAW) / f"{isic_id}.jpg"
    if not path.exists():
        # 占位
        return Image.new("RGB", (THUMB, THUMB), (200, 50, 50))
    img = Image.open(path).convert("RGB")
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    return img.resize((THUMB, THUMB), Image.LANCZOS)


def get_font(size: int) -> ImageFont.ImageFont:
    for name in ["arial.ttf", "Arial.ttf", "C:/Windows/Fonts/arial.ttf",
                 "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_pool(pool_name: str, title: str, candidates: pd.DataFrame):
    """拼接候选 + metadata，输出 PNG。"""
    n     = len(candidates)
    rows  = (n + COLS - 1) // COLS
    W     = COLS * THUMB + (COLS + 1) * GAP
    H     = 60 + rows * (THUMB + META_H + GAP) + GAP
    canvas = Image.new("RGB", (W, H), (250, 250, 250))
    draw   = ImageDraw.Draw(canvas)

    font_title = get_font(20)
    font_meta  = get_font(13)
    font_dim   = get_font(12)
    font_id    = get_font(11)

    draw.text((GAP, 18), title, fill=(20, 20, 20), font=font_title)

    use_deg = pool_name != "hq"

    for i, (_, r) in enumerate(candidates.iterrows()):
        col, row = i % COLS, i // COLS
        x = GAP + col * (THUMB + GAP)
        y = 60 + row * (THUMB + META_H + GAP)

        img = load_thumb(r["isic_id"], use_deg=use_deg)
        canvas.paste(img, (x, y))

        draw.rectangle([x, y, x + 130, y + 18], fill=(0, 0, 0))
        draw.text((x + 4, y + 2), f"[{i:02d}] {r['isic_id']}", fill=(255, 255, 255), font=font_id)

        mx, my = x, y + THUMB + 4

        if pool_name == "hq":
            line1 = f"q_bar = {r['qbar']:.2f}"
            draw.text((mx, my), line1, fill=(30, 30, 30), font=font_meta)
            line2 = f"Std VIB P(mel) = {r['prob_vib']*100:.0f}%  (target = benign)"
            draw.text((mx, my + 18), line2, fill=(30, 130, 30), font=font_meta)
            draw.text((mx, my + 36), f"source: {r['source']}",
                      fill=(110, 110, 110), font=font_meta)
        else:
            # 第 1 行：主降质维度（红色）+ qbar
            pdim = r["primary_dim"]
            line1 = (f"PRIMARY: {DIM_PRETTY.get(pdim, pdim)} = {r['primary_value']:.2f}  "
                     f"|  q_bar = {r['qbar']:.2f}")
            draw.text((mx, my), line1, fill=(190, 30, 30), font=font_meta)
            # 第 2 行：5 维 quality scores（最低维度加亮）
            parts = []
            for c in DIM_COLS:
                v = r[c]
                tag = c[:3].upper()
                parts.append(f"{tag}={v:.2f}{'*' if c == pdim else ''}")
                pass
            draw.text((mx, my + 18), "  ".join(parts), fill=(80, 80, 80), font=font_dim)
            # 第 3 行：Std / QCTS / Δ
            line3 = (f"Std VIB = {r['prob_vib']*100:.0f}%  |  "
                     f"QCTS = {r['prob_qcts']*100:.0f}%  |  "
                     f"Δ = -{r['delta']*100:.0f}pp")
            colour = (190, 30, 30) if r["delta"] > 0.10 else (130, 80, 30)
            draw.text((mx, my + 36), line3, fill=colour, font=font_meta)
            draw.text((mx, my + 54), f"source: {r['source']}",
                      fill=(110, 110, 110), font=font_meta)
            # 主降质维度对应的色框
            COLOR_BY_DIM = {
                "sharpness": (50, 80, 200),
                "brightness": (220, 160, 40),
                "completeness": (140, 70, 180),
                "color_temp": (50, 160, 180),
                "contrast": (200, 80, 80),
            }
            c = COLOR_BY_DIM.get(pdim, (100, 100, 100))
            draw.rectangle([x - 1, y - 1, x + THUMB + 1, y + THUMB + 1], outline=c, width=4)

    out_path = OUT / f"pool_{pool_name}.png"
    canvas.save(out_path, optimize=True)
    print(f"  [saved] {out_path}  ({n} candidates)")


def main():
    print("== Loading aligned tables ==")
    aligned = load_aligned()
    df_lq = aligned["ITB-LQ"]
    df_hq = aligned["ITB-HQ"]
    print(f"  ITB-LQ rows: {len(df_lq)}  |  ITB-HQ rows: {len(df_hq)}")
    print(f"  benign LQ over-confident (StdVIB > 0.85): "
          f"{((df_lq['target']==0) & (df_lq['prob_vib']>0.85)).sum()}")

    cand_lq = pick_lq_pool(df_lq, N_LQ)
    cand_hq = pick_hq_pool(df_hq, N_HQ)

    print(f"  LQ over-confident benign candidates: {len(cand_lq)}")
    print(f"  HQ well-calibrated benign candidates: {len(cand_hq)}")

    render_pool("lq_overconf", "ITB-LQ Over-Confident Benign Pool (Std VIB > 0.50)", cand_lq)
    render_pool("hq",          "ITB-HQ Well-Calibrated Benign Reference Pool",        cand_hq)

    full = pd.concat([cand_lq, cand_hq], ignore_index=True)
    full["selected"] = False
    keep_cols = ["pool", "isic_id", "qbar", "primary_dim", "primary_value",
                 "prob_vib", "prob_qcts", "delta", "target", "source", "level",
                 "sharpness", "brightness", "completeness", "color_temp", "contrast",
                 "image_path", "selected"]
    full = full[[c for c in keep_cols if c in full.columns]]
    csv_path = OUT / "candidates.csv"
    full.to_csv(csv_path, index=False)
    print(f"  [saved] {csv_path}  ({len(full)} total candidates)")
    print()
    print("== NEXT STEP ==")
    print(f"  1. Open pool_lq_overconf.png and pool_hq.png in {OUT}")
    print(f"  2. Edit {csv_path}: set selected=True for the 4 picks (1 HQ + 3 LQ covering Blur/Contrast/Colour)")
    print(f"  3. Run gen_bmvc_figures.py — it reads selected rows for Fig 1")


if __name__ == "__main__":
    main()
