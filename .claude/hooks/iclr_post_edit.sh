#!/usr/bin/env bash
# PostToolUse hook: scan red-line patterns in ICLR tex/md edits.
# Input: JSON {tool_name, tool_input:{file_path, content?}}
# Output: stderr + exit 2 = warn (model sees feedback). Silent on pass.

input=$(cat)
tool=$(echo "$input" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/')

case "$tool" in
  Edit|Write|MultiEdit) ;;
  *) exit 0 ;;
esac

path=$(echo "$input" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/')
norm=$(echo "$path" | tr '\\' '/')

# Only scan ICLR tex/md
case "$norm" in
  *project/meeting/ICLR2027/*.tex|*project/meeting/ICLR2027/*.md|*project/STORY_FRAMEWORK.md|*project/ACCEPTANCE_CRITERIA.md|*project/README.md) ;;
  *) exit 0 ;;
esac

# Convert Windows path to unix for grep
unix_path=$(echo "$norm" | sed 's|^\([A-Za-z]\):/|/\L\1/|')
[ -f "$unix_path" ] || exit 0

# Red line patterns (R1, R2, R4, R8 — most damaging)
patterns='anonymous2025|VisiSkin-Agent|VisiScore-Net|VisiEnhance-Net|Q-VIB\b|DiffBIR|SD-Turbo|TS always reverses|universal reversal|we prove'
hits=$(grep -nE "$patterns" "$unix_path" 2>/dev/null | head -5)

if [ -n "$hits" ]; then
  echo "REDLINE HIT in $path (R1/R2/R4/R8):" 1>&2
  echo "$hits" 1>&2
  echo "Fix before continuing. See project/STORY_FRAMEWORK.md R1-R10." 1>&2
  exit 2
fi

exit 0
