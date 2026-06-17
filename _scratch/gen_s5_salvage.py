# -*- coding: utf-8 -*-
# S5-salvage ideator output script
import json, os

out_path = r"D:\YJ-Agent\project\ideation\runs\2026-06-17_run-001_nca-wm-medseg-uq\03_raw_candidates\S5-salvage.jsonl"
os.makedirs(os.path.dirname(out_path), exist_ok=True)

rows = []
