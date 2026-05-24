# PreToolUse hook: block edits to sealed BMVC dir.
# exit 2 + stderr = block. Silent on pass.

$ErrorActionPreference = 'SilentlyContinue'
$input_json = [Console]::In.ReadToEnd()

if ($input_json -match '"tool_name"\s*:\s*"([^"]+)"') {
    $tool = $matches[1]
} else {
    exit 0
}

if ($tool -notmatch '^(Edit|Write|NotebookEdit|MultiEdit)$') { exit 0 }

if ($input_json -match '"file_path"\s*:\s*"([^"]+)"') {
    $path = $matches[1]
} else {
    exit 0
}

$norm = $path -replace '\\', '/'

if ($norm -match 'project/meeting/BMVC/') {
    # Allow rebuttal/ + camera_ready/
    if ($norm -match 'meeting/BMVC/rebuttal/' -or $norm -match 'meeting/BMVC/camera_ready/') {
        exit 0
    }
    [Console]::Error.WriteLine("BMVC SEALED 2026-05-24. Edit blocked: $path. Use meeting/ICLR2027/ for new work; meeting/BMVC/rebuttal/ for rebuttal.")
    exit 2
}

exit 0
