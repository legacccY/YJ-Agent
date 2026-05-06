"""合并 ISIC 2020 + FitzPatrick17k 质量标签为统一 CSV"""
from pathlib import Path

import pandas as pd

ISIC_CSV = Path("D:/YJ-Agent/data/quality_labels.csv")
FP17K_CSV = Path("D:/YJ-Agent/data/quality_labels_fp17k.csv")
OUTPUT_CSV = Path("D:/YJ-Agent/data/quality_labels_all.csv")


def main() -> None:
    isic = pd.read_csv(ISIC_CSV)
    isic["source"] = "isic2020"

    fp17k = pd.read_csv(FP17K_CSV)
    fp17k["source"] = "fitzpatrick17k"

    merged = pd.concat([isic, fp17k], ignore_index=True)
    merged.to_csv(OUTPUT_CSV, index=False)

    print(f"[OK] 合并完成 → {OUTPUT_CSV}")
    print(f"  ISIC 2020:      {len(isic):>6} 行")
    print(f"  FitzPatrick17k: {len(fp17k):>6} 行")
    print(f"  合计:           {len(merged):>6} 行")
    print("\n按来源和档位分布：")
    print(merged.groupby(["source", "level"]).size().to_string())

    score_cols = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
    print("\n评分统计：")
    print(merged[score_cols].describe().round(3).to_string())


if __name__ == "__main__":
    main()
