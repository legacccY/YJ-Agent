# PostToolUse hook: scan red-line patterns in ICLR tex/md edits.
# exit 2 + stderr = warn. Silent on pass.

$ErrorActionPreference = 'SilentlyContinue'
$input_json = [Console]::In.ReadToEnd()

if ($input_json -match '"tool_name"\s*:\s*"([^"]+)"') {
    $tool = $matches[1]
} else {
    exit 0
}

if ($tool -notmatch '^(Edit|Write|MultiEdit)$') { exit 0 }

if ($input_json -match '"file_path"\s*:\s*"([^"]+)"') {
    $path = $matches[1]
} else {
    exit 0
}

$norm = $path -replace '\\', '/'

# Only scan ICLR tex/md or main project guidance docs
$is_target = ($norm -match 'project/meeting/ICLR2027/.*\.(tex|md)$') -or `
             ($norm -match 'project/(STORY_FRAMEWORK|ACCEPTANCE_CRITERIA|README)\.md$')

if (-not $is_target) { exit 0 }
if (-not (Test-Path $path)) { exit 0 }

$patterns = 'anonymous2025|VisiSkin-Agent|VisiScore-Net|VisiEnhance-Net|Q-VIB\b|DiffBIR|SD-Turbo|TS always reverses|universal reversal|we prove'

$hits = Select-String -Path $path -Pattern $patterns -CaseSensitive:$false -List:$false 2>$null | Select-Object -First 5

if ($hits) {
    [Console]::Error.WriteLine("REDLINE HIT in ${path} (R1/R2/R4/R8):")
    foreach ($h in $hits) {
        [Console]::Error.WriteLine("$($h.LineNumber): $($h.Line)")
    }
    [Console]::Error.WriteLine("Fix before continuing. See project/STORY_FRAMEWORK.md R1-R10.")
    exit 2
}

exit 0
