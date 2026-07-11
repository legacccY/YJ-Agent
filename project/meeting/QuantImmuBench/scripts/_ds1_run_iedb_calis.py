# -*- coding: utf-8 -*-
"""DS1 驱动：复用 run_iedb_calis_official.py 的算法，仅把 3 个路径常量指向 out_ds1。
复现零偏离——不改算法/SUPPORTED_ALLELES/masking/方向，只换输入输出路径。"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_iedb_calis_official as m

m.BACKBONE = m.ROOT / "scripts" / "out_ds1" / "master_backbone_official.csv"
m.WORKDIR = m.ROOT / "scripts" / "out_ds1_official" / "iedb_calis_work"
m.OUT = m.ROOT / "scripts" / "out_ds1_official" / "IEDB_Calis_official.csv"

if __name__ == "__main__":
    m.main()
