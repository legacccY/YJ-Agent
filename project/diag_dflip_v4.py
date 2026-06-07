"""dangerous_flip 根因诊断 (v4 Stage2 DP).

对每个 mask 内黑色素瘤 (ys==1 & pr>0.5, 即 B3 在 ref 上正确报阳),
看 deg/enh 概率走向, 把 flip (pe<0.5) 归因:
  A 退化已翻 (pd<0.5): degradation 自己造成, enhance 没救回 -> enhance 无辜, 任务是 recover 不足
  B enhance 翻  (pd>=0.5, pe<0.5): enhance 主动把阳翻阴 -> 有害 (红线 R8)
另看 flip 的 ref 置信度分布 (是否都卡在 0.5 附近的 borderline).
复用 eval_diag_paired.collect_all (同图同退化, 严格配对).
cwd=project.
"""
import os
import numpy as np
import torch

from eval_diag_paired import build_df, collect_all
from eval_stage2_compare import (load_visienhance, load_visiscore, load_b3,
                                 CFG, CKPTS, VISISCORE, B3)


def main():
    device = torch.device("cpu") if os.environ.get("FORCE_CPU") else torch.device("cuda" if torch.cuda.is_available() else "cpu")
    visiscore = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)
    models = {name: load_visienhance(CFG, path, device) for name, path in CKPTS.items()}
    df = build_df()
    R, D, E, ys = collect_all(models, visiscore, b3, df, device)

    S2 = list(models)[1]                 # Stage2 v4 (DP)
    pr, pd_, pe = R[:, 1], D[:, 1], E[S2][:, 1]
    mask = (ys == 1) & (pr > 0.5)        # B3 在 ref 正确报阳的黑色素瘤
    npos = int(mask.sum())
    flip = mask & (pe < 0.5)
    nflip = int(flip.sum())
    print(f"S2={S2}")
    print(f"mask(ref正确报阳的mel) n={npos}  dangerous_flip n={nflip}  rate={nflip/npos:.4f}\n")

    # 归因: flip 内, 退化已翻 vs enhance 翻
    f_idx = np.where(flip)[0]
    deg_already = int(np.sum(pd_[f_idx] < 0.5))     # A
    enh_caused = int(np.sum(pd_[f_idx] >= 0.5))     # B
    print("--- flip 归因 ---")
    print(f"A 退化已翻(pd<0.5, enhance无辜未救回): {deg_already}/{nflip} = {deg_already/nflip:.3f}")
    print(f"B enhance主动翻(pd>=0.5 -> pe<0.5, 有害R8): {enh_caused}/{nflip} = {enh_caused/nflip:.3f}\n")

    # flip 的 ref 置信度: 是否都 borderline
    print("--- flip 的 ref 置信度 pr 分布 (borderline?) ---")
    print(f"pr  min={pr[f_idx].min():.3f}  median={np.median(pr[f_idx]):.3f}  max={pr[f_idx].max():.3f}")
    print(f"pr<=0.6 占比: {np.mean(pr[f_idx]<=0.6):.3f}   pr<=0.7: {np.mean(pr[f_idx]<=0.7):.3f}\n")

    # enhance 相对 deg 的净效应 (mask 全体, 不只 flip)
    m_idx = np.where(mask)[0]
    print("--- mask 全体 enhance 净效应 (pe - pd) ---")
    delta = pe[m_idx] - pd_[m_idx]
    print(f"pe-pd  mean={delta.mean():+.4f}  median={np.median(delta):+.4f}  "
          f"改善(>0)占比={np.mean(delta>0):.3f}")
    print(f"mask 平均: pr={pr[m_idx].mean():.3f}  pd={pd_[m_idx].mean():.3f}  pe={pe[m_idx].mean():.3f}")

    # 逐例 (flip) 摆出来
    print("\n--- 逐例 flip (pr -> pd -> pe) ---")
    order = f_idx[np.argsort(pr[f_idx])]
    for i in order:
        tag = "B-enh翻" if pd_[i] >= 0.5 else "A-退化翻"
        print(f"  pr={pr[i]:.3f}  pd={pd_[i]:.3f}  pe={pe[i]:.3f}  [{tag}]")


if __name__ == "__main__":
    main()
