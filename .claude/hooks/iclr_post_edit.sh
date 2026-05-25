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

# Only scan ICLR tex/md (full check) or main project docs (writing-only check)
is_tex=0; is_doc=0
case "$norm" in
  *project/meeting/ICLR2027/*.tex|*project/meeting/ICLR2027/*.md) is_tex=1 ;;
  *project/STORY_FRAMEWORK.md|*project/ACCEPTANCE_CRITERIA.md|*project/README.md) is_doc=1 ;;
  *) exit 0 ;;
esac

# Convert Windows path to unix for grep
unix_path=$(echo "$norm" | sed 's|^\([A-Za-z]\):/|/\L\1/|')
[ -f "$unix_path" ] || exit 0

# tex: full redline. planning docs: writing-quality only (model names are legitimate in tracking docs)
if [ "$is_tex" = "1" ]; then
  patterns='anonymous2025|VisiSkin-Agent|VisiScore-Net|VisiEnhance-Net|Q-VIB\b|DiffBIR|SD-Turbo|TS always reverses|universal reversal|we prove|\bBayesian\b|doctors? confirmed|clinically validated|clinical decision support'
else
  patterns='anonymous2025|TS always reverses|universal reversal|doctors? confirmed|clinically validated|clinical decision support'
fi
hits=$(grep -nE "$patterns" "$unix_path" 2>/dev/null | head -5)

if [ -n "$hits" ]; then
  echo "REDLINE HIT in $path (R1/R2/R4/R8):" 1>&2
  echo "$hits" 1>&2
  echo "Fix before continuing. See project/STORY_FRAMEWORK.md R1-R10." 1>&2
  exit 2
fi

exit 0
