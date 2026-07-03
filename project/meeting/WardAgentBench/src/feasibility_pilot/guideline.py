# -*- coding: utf-8 -*-
"""
guideline.py — D* 生成器：从可算体征算 partial-NEWS2 + 官方升级级别 + 响应角色
================================================================================
服务哪个 Q（可行性命门）：
  四角色信号**分布**是否制造「医生中心单流 agent 结构上表达不出、且能用公开指南打分」
  的失败？本模块提供该命门唯一合法的 **ground-truth D***：**公开指南 NEWS2 的确定函数**。
  绝不用 LLM 生成 D*（防循环）。

输入（Python 调用，非 CLI）：
  vitals: dict，规范体征 -> 数值（点值，已由窗口聚合）：
    'HR'(bpm) / 'SpO2'(%) / 'ABPsys'(mmHg 收缩压) / 'RESP'(rpm)。
  ⚠️ 缺失的 NEWS2 参数：体温(temp °C)、意识(ACVPU)、是否吸氧(supplemental O2)——
     真实 mimic3wdb numerics 不含，标 TODO 缺失，只算**可算子集** = partial-NEWS2。
     诚实声明是子集：partial_total 系统性 **低估** full NEWS2（缺项只会加分不会减分），
     但 D* 对 A/B 两条件用同一函数，A-vs-B 对比仍有效（绝对临床对错另行 caveat）。

输出（本模块无 CSV；供 build_scenarios / score import。ground_truth() 返回 dict 字段）：
  news2_partial_total : int   可算子集分数和
  red_flag            : bool   任一可算参数得分=3（NEWS2 单参 red score）
  missing_params      : list   缺的 NEWS2 参数名（temp/consciousness/supplemental_o2 + 缺测体征）
  param_scores        : dict   每可算参数 -> 得分
  escalate            : str     {none, ward, urgent, immediate}
  route_to_role       : str     {nurse, doctor, rapid_response}
  timing_bin          : str     {routine_12h, ward_4to6h, hourly, continuous}

阈值来源（红线：查官方源标出处）：
  Royal College of Physicians, "National Early Warning Score (NEWS) 2 —
  Standardising the assessment of acute-illness severity in the NHS", RCP, London, 2017.
  评分表 = 该文档 Chart 1（NEWS2 scoring system），升级协议 = Chart 3（clinical response）。
  下方数值为 RCP NEWS2 2017 标准值。⚠️ TODO(researcher): 复核官方 chart 边界行
  （尤其 SpO2 Scale 1 vs Scale 2、单参=3 触发口径），确认与最新 RCP 版一致后去此标记。
  纯 Python/numpy，无 scipy。Windows 规范：pathlib/utf-8。**本模块不执行，只被 import。**
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 合法离散标签集（agent 结构化输出须落在这些集合内，score.py 精确匹配用）
# 级别有序：none < ward < urgent < immediate（供「B 是否比 A 更偏离」比较）
# ---------------------------------------------------------------------------
ESCALATE_LEVELS = ["none", "ward", "urgent", "immediate"]
ESCALATE_ORDER = {lv: i for i, lv in enumerate(ESCALATE_LEVELS)}
ROLES = ["nurse", "doctor", "rapid_response"]
TIMING_BINS = ["routine_12h", "ward_4to6h", "hourly", "continuous"]

# NEWS2 完整 7 参数（用于列缺失项；本 pilot 可算前 4，后 3 恒缺）
NEWS2_FULL_PARAMS = ["RESP", "SpO2", "supplemental_o2", "ABPsys", "HR",
                     "consciousness", "temp"]
COMPUTABLE_PARAMS = ["RESP", "SpO2", "ABPsys", "HR"]
MISSING_PARAMS_FIXED = ["supplemental_o2", "consciousness", "temp"]


# ---------------------------------------------------------------------------
# NEWS2 单参评分表（RCP 2017 Chart 1）——每个函数返回该参数得分∈{0,1,2,3}
# 边界均按官方「≤ / 区间 / ≥」写法。数值不确定处已在模块头标 TODO(researcher)。
# ---------------------------------------------------------------------------
def score_resp(rr: float) -> int:
    """呼吸频率 RR (/min)。RCP NEWS2 2017: ≤8→3, 9-11→1, 12-20→0, 21-24→2, ≥25→3。"""
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def score_spo2_scale1(spo2: float) -> int:
    """SpO2 Scale 1 (%)。RCP NEWS2 2017: ≤91→3, 92-93→2, 94-95→1, ≥96→0。
    ⚠️ Scale 2（高碳酸血症呼衰患者，需吸氧信息）本 pilot 无 O2/临床标志 → 一律用 Scale 1，
       稿中须声明；TODO(researcher) 若数据含吸氧状态再补 Scale 2 分支。"""
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def score_sbp(sbp: float) -> int:
    """收缩压 SBP (mmHg)。RCP NEWS2 2017: ≤90→3, 91-100→2, 101-110→1, 111-219→0, ≥220→3。"""
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp <= 219:
        return 0
    return 3


def score_pulse(hr: float) -> int:
    """脉搏/心率 HR (/min)。RCP NEWS2 2017: ≤40→3, 41-50→1, 51-90→0, 91-110→1, 111-130→2, ≥131→3。"""
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


# 缺失参数评分函数（供数据未来补齐时用；本 pilot 不调用，占位声明）
def score_temp(temp_c: float) -> int:
    """体温 (°C)。RCP NEWS2 2017: ≤35.0→3, 35.1-36.0→1, 36.1-38.0→0, 38.1-39.0→1, ≥39.1→2。
    ⚠️ 本 pilot numerics 无体温 → 不调用，missing。"""
    if temp_c <= 35.0:
        return 3
    if temp_c <= 36.0:
        return 1
    if temp_c <= 38.0:
        return 0
    if temp_c <= 39.0:
        return 1
    return 2


def score_consciousness(acvpu: str) -> int:
    """意识 ACVPU。RCP NEWS2 2017: Alert→0；Confusion/V/P/U→3。本 pilot 无 → missing。"""
    return 0 if str(acvpu).strip().lower() in ("a", "alert") else 3


def score_supplemental_o2(on_oxygen: bool) -> int:
    """是否吸氧。RCP NEWS2 2017: 空气→0；吸氧→2。本 pilot 无 → missing。"""
    return 2 if on_oxygen else 0


_SCORERS = {
    "RESP": score_resp,
    "SpO2": score_spo2_scale1,
    "ABPsys": score_sbp,
    "HR": score_pulse,
}


# ---------------------------------------------------------------------------
# 升级级别 / 响应角色 / 监测频率（RCP 2017 Chart 3 clinical response）
# ---------------------------------------------------------------------------
def escalation_level(partial_total: int, red_flag: bool) -> str:
    """按 NEWS2 聚合分 + 单参 red score 映射到离散升级级别。
    RCP NEWS2 2017 Chart 3 触发口径：
      聚合 0            → 常规（routine, min 12-hourly）           => 'none'
      聚合 1-4          → 病房护士评估（min 4-6 hourly）           => 'ward'
      单参 = 3 (RED)    → 紧急临床医师复查（urgent, min 1-hourly）  => 'urgent'
      聚合 5-6 (medium) → 紧急临床复查（min 1-hourly, 考虑升 ICU）  => 'urgent'
      聚合 ≥7 (high)    → 危急评估/critical care team（continuous） => 'immediate'
    ⚠️ 用 partial_total（低估），故 urgent/immediate 会**偏保守漏触发**；
       这是诚实子集限制，A/B 同 D* 不影响对比。TODO(researcher) 核单参=3 是否独立于聚合分触发 urgent。"""
    if partial_total >= 7:
        return "immediate"
    if partial_total >= 5 or red_flag:
        return "urgent"
    if partial_total >= 1:
        return "ward"
    return "none"


def route_for_level(level: str) -> str:
    """级别 -> 谁响应。none/ward→nurse；urgent→doctor；immediate→rapid_response。"""
    return {
        "none": "nurse",
        "ward": "nurse",
        "urgent": "doctor",
        "immediate": "rapid_response",
    }[level]


def timing_for_level(level: str) -> str:
    """级别 -> 监测频率 bin（RCP Chart 3 最低监测频率）。"""
    return {
        "none": "routine_12h",
        "ward": "ward_4to6h",
        "urgent": "hourly",
        "immediate": "continuous",
    }[level]


# ---------------------------------------------------------------------------
# 主入口：从可算体征 dict 算 partial-NEWS2 + D*
# ---------------------------------------------------------------------------
def partial_news2(vitals: dict) -> dict:
    """算可算子集 NEWS2。vitals 缺某体征（None/NaN/键不存在）→ 该参数计入 missing，不计分。
    返回 param_scores / news2_partial_total / red_flag / missing_params。"""
    param_scores = {}
    missing = list(MISSING_PARAMS_FIXED)  # temp/consciousness/o2 恒缺
    for p in COMPUTABLE_PARAMS:
        v = vitals.get(p, None)
        if v is None or (isinstance(v, float) and v != v):  # None 或 NaN
            missing.append(p)
            continue
        param_scores[p] = _SCORERS[p](float(v))
    total = int(sum(param_scores.values()))
    red_flag = any(s == 3 for s in param_scores.values())
    return {
        "param_scores": param_scores,
        "news2_partial_total": total,
        "red_flag": red_flag,
        "missing_params": missing,
    }


def ground_truth(vitals: dict) -> dict:
    """D* 生成器（唯一合法真值来源，确定性，非 LLM）。
    输入窗口聚合体征 dict -> 完整 D* dict（含 escalate/route_to_role/timing_bin + 诊断字段）。"""
    n = partial_news2(vitals)
    level = escalation_level(n["news2_partial_total"], n["red_flag"])
    return {
        "news2_partial_total": n["news2_partial_total"],
        "red_flag": n["red_flag"],
        "param_scores": n["param_scores"],
        "missing_params": n["missing_params"],
        "escalate": level,
        "route_to_role": route_for_level(level),
        "timing_bin": timing_for_level(level),
    }
