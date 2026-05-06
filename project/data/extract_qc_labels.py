"""从 FitzPatrick17k CSV 提取皮肤科医生 QC 标注，生成校验集"""
from pathlib import Path

import pandas as pd

FP17K_CSV = Path("D:/YJ-Agent/data/raw/fitzpatrick17k/fitzpatrick17k.csv")
IMG_DIR = Path("D:/YJ-Agent/data/raw/fitzpatrick17k/images")
OUTPUT_CSV = Path("D:/YJ-Agent/data/expert_qc_labels.csv")

# QC 标注 → 质量等级映射
QC_TO_QUALITY = {
    "1 Diagnostic": "high",
    "2 Characteristic": "high",
    "5 Potentially": "medium",
    "4 Other": "low",
    "3 Wrongly labelled": None,  # 排除
}


def main() -> None:
    df = pd.read_csv(FP17K_CSV)
    qc_df = df[df["qc"].notna()].copy()

    rows = []
    for _, row in qc_df.iterrows():
        quality = QC_TO_QUALITY.get(row["qc"])
        if quality is None:
            continue
        img_path = IMG_DIR / f"{row['md5hash']}.jpg"
        if not img_path.exists():
            continue
        rows.append({
            "image_path": str(img_path),
            "md5hash": row["md5hash"],
            "fitzpatrick_scale": row["fitzpatrick_scale"],
            "label": row["label"],
            "qc_raw": row["qc"],
            "expert_quality": quality,
        })

    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT_CSV, index=False)
    print(f"[OK] {len(result)} 张专家标注图 → {OUTPUT_CSV}")
    print(result["expert_quality"].value_counts())
    print(result["fitzpatrick_scale"].value_counts().sort_index())


if __name__ == "__main__":
    main()
