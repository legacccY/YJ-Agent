# UserPromptSubmit hook: keyword-triggered reminder + Opus-in-ICLR caveman-off signal.
# Silent unless triggered.

$ErrorActionPreference = 'SilentlyContinue'
$input_json = [Console]::In.ReadToEnd()

if ($input_json -match '"prompt"\s*:\s*"([^"]*)"') {
    $prompt = $matches[1]
} else {
    $prompt = ""
}

if ($input_json -match '"cwd"\s*:\s*"([^"]+)"') {
    $cwd = $matches[1]
} else {
    exit 0
}

$norm = $cwd -replace '\\', '/'
if ($norm -notmatch 'YJ-Agent') { exit 0 }

$out = ""

# Opus-in-ICLR caveman override (cwd within project/)
if ($norm -match 'YJ-Agent/project') {
    $out += "[Opus-in-ICLR rule] CAVEMAN MODE OVERRIDE — Opus 在 project/ 内用正常中文，不 caveman。Sonnet/Haiku subagent 可继续 caveman。`n"
}

# Keyword triggers
if ($prompt -match '写论文|写tex|写 tex|ICLR 论文|draft|章节|Section|main paper') {
    $out += "[Keyword: 论文/tex] Before edit meeting/ICLR2027/*.tex: Read STORY_FRAMEWORK.md (§1-§9 锁定) + DATA_INVENTORY.md (数字 csv 源). 数字必须 csv 核算.`n"
}

if ($prompt -match '跑实验|开始训练|启动训练|train|实验|config|重训') {
    $out += "[Keyword: 训练] 用 /loop /run-experiment 触发 (CLAUDE.md 规范). Start-Process 开新窗口避免阻塞.`n"
}

if ($prompt -match '改 BMVC|改BMVC|BMVC 加|改 itb_paper|改itb_paper') {
    $out += "[Keyword: BMVC] BMVC SEALED. 任何改动走 meeting/BMVC/rebuttal/ 或 meeting/ICLR2027/.`n"
}

if ($prompt -match '扩散|diffusion|DiffBIR|SD-Turbo|Stable Diffusion') {
    $out += "[Keyword: 扩散] R8 红线: 扩散模型禁用于皮肤镜增强 (伪影). 只能在 §8.2 作为对照警示出现.`n"
}

if ($out -ne "") {
    Write-Output $out
}
exit 0
