# -*- coding: utf-8 -*-
"""把 code/ 目录加入 sys.path，使 tests 可 import probes/vindr_loader/eval_collect/ckpt_probe_driver。"""
import os
import sys

_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)
