# -*- coding: utf-8 -*-
"""
alarm_thresholds.py — KS-3 命门共享阈值/告警定义模块
=====================================================
服务 WardAgentBench KS-3 数据命门 kill-shot（候选 B）。
本模块只放"告警器定义 + 阈值族"，被 02/03 脚本 import。

⚠️ 红线（超参禁臆想）：
  - PhysioNet 2015 五类致命心律失常定义 = 权威（ANSI/AAMI EC13，Challenge 2015 官方规则），确证可用。
  - 通用体征阈值告警（HR/SpO2/ABP/RR）的**确切数值**需查官方监护标准 / Chromik et al.
    "Extracting Alarm Events from the MIMIC-III Clinical Database"（本项目指定派生法）。
    下方 VITAL_THRESHOLD_FAMILIES 的具体上下限**属占位**，每个都标 TODO，
    主线/researcher 需核对 Chromik 论文 Table 或 Philips IntelliVue / GE 默认值后替换。
    **绝不当已确认值汇报。** Q2 稳健性本就跨阈值族扫，占位不影响"共触发是否存在"的定性结论，
    但复合 FAR 的绝对数值在阈值锁定前只作方向性参考。
"""

# ---------------------------------------------------------------------------
# PhysioNet 2015 Challenge —— 五类致命心律失常告警定义（权威，供 01 脚本参照 Q3）
# 来源：Clifford et al., "The PhysioNet/Computing in Cardiology Challenge 2015:
#       Reducing False Arrhythmia Alarms in the ICU"，规则同 ANSI/AAMI EC13-2002。
# 注：这 5 类是**单告警 / 单段**结构（每条 record 仅 1 个告警，onset 固定在第 300s），
#     跨段分布、彼此不在同一时间窗共触发 —— 正是 Q3 要坐实的"无法供共触发标注"。
# 真/假金标写在每条 .hea 的注释行（True alarm / False alarm），非本模块派生。
# ---------------------------------------------------------------------------
PHYSIONET2015_ALARM_TYPES = {
    "Asystole":        "无 QRS 持续 >= 4 s",
    "Bradycardia":     "心率 <= 40 bpm 持续 5 个连续心搏（Extreme Bradycardia）",
    "Tachycardia":     "心率 >= 140 bpm 持续 17 个连续心搏（Extreme Tachycardia）",
    "Ventricular_Tachycardia":     ">= 5 个连续室性搏动且 HR > 100 bpm",
    "Ventricular_Flutter_Fib":     "颤动/扑动波形持续 >= 4 s",
}

# .hea 注释行里的告警短码（PhysioNet 2015 官方命名），用于解析
PHYSIONET2015_CODE_MAP = {
    "Asystole": "Asystole",
    "Bradycardia": "Bradycardia",
    "Tachycardia": "Tachycardia",
    "Ventricular_Tachycardia": "Ventricular_Tachycardia",
    "Ventricular_Flutter_Fib": "Ventricular_Flutter_Fib",
}

# ---------------------------------------------------------------------------
# MIMIC-III Waveform 派生阈值告警器（供 02/03 脚本，Q1/Q2）
# 每个告警器 = 一个体征信号 + 上下限 + 最短持续时间（去 artifact）。
# 我们从 numerics record（*n，通常 1 Hz：HR / SpO2 / ABP / RESP）派生阈值越界事件。
#
# 阈值族（threshold families）= 同一批告警器的不同松紧档，Q2 靠"换族不翻"检验稳健性。
# ✅ default 族数值 = Philips IntelliVue 官方默认（已核，见下 VITAL_THRESHOLD_FAMILIES 引用）；
#    conservative/liberal + sustain + 共触发窗 = 项目设计选择（R8 稿中声明）。
# 信号名沿用 MIMIC-III numerics 常见记法：'HR'（bpm）、'SpO2'/'%SpO2'（%）、
#   'ABPsys'/'ABP SYS'（mmHg 收缩压）、'RESP'（rpm）。实际列名以 record 头为准（脚本会做别名匹配）。
# 持续时间（sustain_s）默认参照"数秒级"去除瞬时 artifact —— 具体秒数亦需核 Chromik，标 TODO。
# ---------------------------------------------------------------------------

# 信号别名表：不同 MIMIC-III record 头里同一体征的多种写法 -> 规范键
SIGNAL_ALIASES = {
    "HR":   ["HR", "Heart Rate", "Pulse"],
    "SpO2": ["SpO2", "%SpO2", "SPO2", "SaO2"],
    "ABPsys": ["ABPSys", "ABP SYS", "ABPs", "ART Sys", "NBPSys", "ABP", "ART"],
    "RESP": ["RESP", "Resp", "RR", "AWRR"],
}

# 每个阈值族：signal -> dict(low, high, sustain_s)
# low/high 为 None 表示该方向不设限（如 SpO2 只关心过低）。
#
# 来源锚定（researcher 2026-07-02 核实）：
#  - **default 族 = Philips IntelliVue MP20-90 成人出厂默认告警限**（一手手册 IFU ch.39,
#    medaval.ie Philips-MP20-MP90-Manual.pdf p.460-466）：HR 50/120、SpO2 low 90(Desat 80)、
#    ABPsys 90/160、RESP 8/30。GE Solar 8000i(UCSF, Drew 2014 PMC4206416) 交叉：HR high 130、
#    其余一致 → default 用 Philips HR high=120、conservative 用 GE HR high=130。
#  - ⚠️ Chromik et al.（本项目原指定派生法）**不提供固定阈值表**：它读 MIMIC CHARTEVENTS 里
#    医生逐病人动态设定的 high/low itemid（HR 220046/220047, NBPs 223751/223752,
#    SpO2 223769/223770），只 3 信号无 RR、即时触发无 sustain。故固定阈值族改锚 Philips 官方默认。
#  - **sustain_s / conservative / liberal 松紧 / COTRIGGER_WINDOW_S = 项目设计选择（非官方默认）**：
#    Philips 仅 SpO2 有 10s alarm delay（Desat 20s）、ABP artifact-suppr 60s，HR/RESP 越限即时无 delay。
#    统一 sustain 用 SpO2 的 10s 作去-artifact 类比（design choice）。R8：稿中须声明这些为设计选择。
#  - TODO: RR 数值仅 Philips 单源（GE 未给数值）；HR/ABP 官方无越限 sustain。
VITAL_THRESHOLD_FAMILIES = {
    # ---- 族 1：default = Philips IntelliVue 成人出厂默认（官方，见上引用）----
    "default": {
        "HR":     {"low": 50,  "high": 120, "sustain_s": 10},   # Philips IFU p.460 (HR 50/120)
        "SpO2":   {"low": 90,  "high": None, "sustain_s": 10},   # Philips IFU p.464 (low 90, delay 10s)
        "ABPsys": {"low": 90,  "high": 160, "sustain_s": 10},    # Philips IFU p.465 (ABP sys 90/160)
        "RESP":   {"low": 8,   "high": 30,  "sustain_s": 10},    # Philips IFU p.463 (RR 8/30)
    },
    # ---- 族 2：conservative（更宽，少报）= GE-UCSF 交叉 + 下浮（设计选择，声明）----
    "conservative": {
        "HR":     {"low": 40,  "high": 130, "sustain_s": 15},    # HR high=GE 130(Drew2014); 其余设计下浮
        "SpO2":   {"low": 85,  "high": None, "sustain_s": 15},   # 设计选择
        "ABPsys": {"low": 80,  "high": 180, "sustain_s": 15},    # 设计选择
        "RESP":   {"low": 6,   "high": 35,  "sustain_s": 15},    # 设计选择
    },
    # ---- 族 3：liberal（更严，多报）= 设计选择（声明，非官方）----
    "liberal": {
        "HR":     {"low": 55,  "high": 110, "sustain_s": 5},     # 设计选择
        "SpO2":   {"low": 92,  "high": None, "sustain_s": 5},    # 设计选择
        "ABPsys": {"low": 100, "high": 150, "sustain_s": 5},     # 设计选择
        "RESP":   {"low": 10,  "high": 28,  "sustain_s": 5},     # 设计选择
    },
}

# 共触发时间窗宽度（秒）：判定"≥2 类告警在同一窗内活跃"。
# TODO 核 Chromik / 临床合理窗（常见 10~60 s），占位 30 s。
COTRIGGER_WINDOW_S = 30

# 弱结局代理（Q2 定真/假，波形可自定义弱代理，非专家标注）：
#   persistent_derangement_s = 告警后体征持续紊乱达此秒数 -> 判"真(true)"；否则判"假/artifact"。
# ⚠️ R8：这是**派生弱代理**，非结局金标；完整结局代理需 CITI matched 临床结局，稿中必声明。
# TODO 核合理阈值，占位 120 s。
WEAK_PROXY_PERSIST_S = 120


def canonicalize_signal(sig_name):
    """把 record 头里的原始信号名映射到规范键（HR/SpO2/ABPsys/RESP），匹配不到返回 None。"""
    s = sig_name.strip()
    s_low = s.lower()
    for canon, aliases in SIGNAL_ALIASES.items():
        for a in aliases:
            if s_low == a.lower():
                return canon
    return None
