# -*- coding: utf-8 -*-
"""DS1 驱动：复用 run_deepimmuno_official.py 的 prep/parse，仅把工作目录/输入指向 out_ds1。
复现零偏离——算法/HLA 转换/9-10mer 过滤全不改，只换路径。
用法: python _ds1_run_deepimmuno.py {prep|parse}
中间的 WSL CNN 推理由主线单独跑（deepimmuno env）。"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_deepimmuno_official as m

ROOT = m.ROOT
WORK = ROOT / "scripts" / "out_ds1_official" / "immml_work"
m.WORK = WORK
m.UNIQ = ROOT / "scripts" / "out_ds1" / "newtools" / "uniq_pep_hla.csv"
m.INP = WORK / "deepimmuno_input.csv"
m.HMAP = WORK / "deepimmuno_hla_map.csv"
m.RESULT = WORK / "deepimmuno_out" / "deepimmuno-cnn-result.txt"
m.RAW = WORK / "deepimmuno_raw_official.csv"

if __name__ == "__main__":
    {"prep": m.prep, "parse": m.parse}[sys.argv[1]]()
