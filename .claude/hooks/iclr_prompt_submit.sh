#!/usr/bin/env bash
# UserPromptSubmit hook: keyword-triggered reminder + opus caveman-off in ICLR.
# Silent unless triggered. Output: stdout = injected as additional context.

input=$(cat)
prompt=$(echo "$input" | grep -oE '"prompt"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
cwd=$(echo "$input" | grep -oE '"cwd"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/')
norm=$(echo "$cwd" | tr '\\' '/')

# Only fire inside YJ-Agent
case "$norm" in
  */YJ-Agent*|*\YJ-Agent*) ;;
  *) exit 0 ;;
esac

out=""

# Opus caveman off when in ICLR-related path (no easy model detection at hook time; rely on user invoking opus)
# Output override: explicit instruction supersedes caveman injection
case "$norm" in
  */YJ-Agent/project*|*YJ-Agent\project*)
    out="${out}[Opus-in-ICLR rule] CAVEMAN MODE OVERRIDE — Opus 在 project/ 内用正常中文，不 caveman。Sonnet/Haiku subagent 可继续 caveman。\n"
    ;;
esac

# Keyword triggers (quoted to allow spaces inside patterns)
case "$prompt" in
  *"写论文"*|*"写tex"*|*"写 tex"*|*"ICLR 论文"*|*"draft"*|*"章节"*|*"Section"*|*"main paper"*)
    out="${out}[Keyword: 论文/tex] Before edit meeting/ICLR2027/*.tex: Read STORY_FRAMEWORK.md (§1-§9 锁定) + DATA_INVENTORY.md (数字 csv 源). 数字必须 csv 核算.\n"
    ;;
esac

case "$prompt" in
  *"跑实验"*|*"开始训练"*|*"启动训练"*|*"train"*|*"实验"*|*"config"*|*"重训"*)
    out="${out}[Keyword: 训练] 用 /loop /run-experiment 触发 (CLAUDE.md 规范). Start-Process 开新窗口避免阻塞.\n"
    ;;
esac

case "$prompt" in
  *"改 BMVC"*|*"改BMVC"*|*"BMVC 加"*|*"改 itb_paper"*|*"改itb_paper"*)
    out="${out}[Keyword: BMVC] BMVC SEALED. 任何改动走 meeting/BMVC/rebuttal/ 或 meeting/ICLR2027/.\n"
    ;;
esac

case "$prompt" in
  *"扩散"*|*"diffusion"*|*"DiffBIR"*|*"SD-Turbo"*|*"Stable Diffusion"*)
    out="${out}[Keyword: 扩散] R8 红线: 扩散模型禁用于皮肤镜增强 (伪影). 只能在 §8.2 作为对照警示出现.\n"
    ;;
esac

[ -n "$out" ] && printf "%b" "$out"
exit 0
