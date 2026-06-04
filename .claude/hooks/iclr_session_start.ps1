# SessionStart hook: brief reminder if cwd is YJ-Agent project.
# Silent if not in YJ-Agent. Output to stdout = additional context.

$ErrorActionPreference = 'SilentlyContinue'
$input_json = [Console]::In.ReadToEnd()

if ($input_json -match '"cwd"\s*:\s*"([^"]+)"') {
    $cwd = $matches[1]
} else {
    exit 0
}

$norm = $cwd -replace '\\', '/'
if ($norm -notmatch 'YJ-Agent') { exit 0 }

Write-Output "[ICLR 2027 大项目 active] Read order if writing tex/数字: project/README.md → STORY_FRAMEWORK.md → ACCEPTANCE_CRITERIA.md → DATA_INVENTORY.md → PROJECT_LOG.md. BMVC SEALED. Opus 在 project/ 内默认开 caveman，用户说「关」才关。"
exit 0
