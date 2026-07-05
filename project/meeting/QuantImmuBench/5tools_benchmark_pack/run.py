# -*- coding: utf-8 -*-
"""
run.py — 一键复现入口
  1) 跑 evaluate_three_tier.py，从 5 工具输出重算三层横评表
  2) 自动与 expected_results/ 逐值核对，打印 PASS/FAIL
用法：python run.py
"""
import os
import pandas as pd
import evaluate_three_tier as ev

HERE = os.path.dirname(os.path.abspath(__file__))


def validate():
    got = pd.read_csv(os.path.join(HERE, "results", "metrics_three_tier.csv")).set_index("Tool")
    exp = pd.read_csv(os.path.join(HERE, "expected_results", "metrics_three_tier.csv")).set_index("Tool")
    cols = ["FisherZ_rho", "Global_rho", "AUC", "FisherZ_95CI", "n_peptides_covered"]
    ok = True
    for t in exp.index:
        for c in cols:
            a, b = got.loc[t, c], exp.loc[t, c]
            match = (a == b) if isinstance(a, str) else abs(float(a) - float(b)) < 1e-4
            if not match:
                ok = False
                print("  DIFF %s.%s: got=%s expected=%s" % (t, c, a, b))
    return ok


if __name__ == "__main__":
    ev.main()
    print("\n=== 与 expected_results/ 核对 ===")
    if validate():
        print("PASS ✓ 复现结果与 PPT 参考表逐值一致（Fisher-Z / 全局 Spearman / AUC / 95%CI 全对上）")
    else:
        print("FAIL ✗ 有数值不一致，见上方 DIFF")
