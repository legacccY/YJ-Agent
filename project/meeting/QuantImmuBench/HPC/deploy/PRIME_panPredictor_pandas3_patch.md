# MixMHCpred panPredictor.py pandas 3.0 兼容补丁（PRIME 依赖）

> 服务 QuantImmuBench 改动②/③ 全量重跑 · slice_finish · PRIME/B2706
> 打补丁：2026-07-07（用户拍板「修工具(有验证)」）

## 问题
PRIME 依赖 MixMHCpred。对**无原生 PWM 的等位**（本 benchmark 仅 **HLA-B\*27:06 = B2706**）走
pan-predictor 路径 `MixMHCpred/code/panPredictor.py::Blosum_Corr_pred`，在 env `envs/prime`
的 **pandas 3.0.3** 上硬崩 `KeyError: 0`（单肽 600s 超时不出结果）。24 个有原生 PWM 的等位不走此路，正常。

## 根因
`panPredictor.py` 为老 pandas 写。PWM 是 `pd.DataFrame(index=氨基酸字符串, columns=1..PL整数)`
（见 `arrays_to_pwm_dataframes` L134）。`PWM[i+1]` 取列 → Series（**氨基酸字符串索引**），
再 `[j]`/`[z]`（j,z=0..19 意图**按位置**取第 j 个氨基酸）→ pandas 3.0 把整数当**标签**查 → `KeyError:0`。
（`blosum_t` 是 numpy 数组，`blosum_t[j][z]` 位置索引正常，不动。）

## 补丁（2 处，`Blosum_Corr_pred` 内）
```
L151:  x = (N * PWM[i+1][j])            →  x = (N * PWM[i+1].iloc[j])
L154:  a+= (blosum_t[j][z]*PWM[i+1][z]) →  a+= (blosum_t[j][z]*PWM[i+1].iloc[z])
```
`.iloc[j]` 恢复位置访问 = 工具原意（遍历 20 个氨基酸），零语义偏离。

## 文件
- HPC: `/gpfs/work/bio/jiayu2403/quantimmu/tools_repos/MixMHCpred/code/panPredictor.py`
- 备份: 同目录 `panPredictor.py.bak_pandas3_20260707`（打补丁前原版）

## 验证
单肽 AAEELRSIL：补丁前 600s 超时 KeyError:0 → 补丁后 **7s rc=0**，输出 `Score_B2706=0.005186 %Rank=8.798`（合理 PRIME 值）。B2706 全 99 肽 MT+WT 随后正常跑通。

## 影响面
只影响 pan-predictor 路径（本 benchmark 唯一走此路=B2706）。24 有 PWM 等位不受影响。
其他窗若用 MixMHCpred pan-predictor（PWM-less 等位）也受益。
