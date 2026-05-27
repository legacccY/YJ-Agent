#!/usr/bin/env bash
# CLI red-line scanner for ICLR 2027 paper material.
#
# Scans:
#   - project/meeting/ICLR2027/**/*.{tex,md}   (paper drafts)
#   - project/STORY_FRAMEWORK.md, ACCEPTANCE_CRITERIA.md, README.md (guidance docs)
#
# Detects R1/R2/R4/R8 red-line phrases (must be sanitised before submission):
#   R1: TS always reverses / universal reversal
#   R2: "we prove" used informally
#   R4: anonymous2025* / VisiScore-Net / VisiEnhance-Net / Q-VIB / VisiSkin-Agent
#   R8: DiffBIR / SD-Turbo (diffusion-based enhancement, methodology red line)
#
# Exit:
#   0 = clean
#   2 = red-line hit (stderr lists offending file:line)
#
# Usage:
#   bash project/scripts/iclr_grep_redlines.sh             # scan all default targets
#   bash project/scripts/iclr_grep_redlines.sh path1 path2 # scan specific files
#
# Sister hook (auto-runs on Edit/Write): .claude/hooks/iclr_post_edit.sh

set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

# Red-line patterns (kept in lockstep with .claude/hooks/iclr_post_edit.{sh,js}).
# Anchored where appropriate to reduce false positives in citation lists / Notation tables.
# Includes R1-R10 (STORY_FRAMEWORK §防御性写作硬规则) + L19 adversarial review surface
# (R2 Bayesian framing / R3 clinical realism / R10 safety language).
PATTERNS='anonymous2025|VisiSkin-Agent|VisiScore-Net|VisiEnhance-Net|\bQ-VIB\b|DiffBIR|SD-Turbo|TS always reverses|universal reversal|\bwe prove\b|\bBayesian\b|doctors? confirmed|clinically validated|clinical decision support'

# Allowed contexts (Notation / framework files are allowed to define the internal terms).
# Detection logic: skip lines that contain "// NOTE: redline-allowed" marker, so authors
# can opt-out individual references (e.g., when citing BMVC as a related work).
SKIP_MARKER='redline-allowed'

# Default scan targets: paper material only (where red lines must be sanitised).
# Guidance docs (STORY_FRAMEWORK / ACCEPTANCE_CRITERIA / README) legitimately
# contain the patterns as definitions of what NOT to write — scan them only
# with --include-guidance.
default_targets=()
if [ -d "project/meeting/ICLR2027" ]; then
  while IFS= read -r f; do
    default_targets+=("$f")
  done < <(find "project/meeting/ICLR2027" -type f \( -name '*.tex' -o -name '*.md' \) 2>/dev/null)
fi

include_guidance=0
positional=()
for arg in "$@"; do
  case "$arg" in
    --include-guidance) include_guidance=1 ;;
    -h|--help)
      sed -n '1,30p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) positional+=("$arg") ;;
  esac
done

if [ "${#positional[@]}" -gt 0 ]; then
  targets=("${positional[@]}")
else
  targets=("${default_targets[@]}")
  if [ "$include_guidance" -eq 1 ]; then
    targets+=(
      "project/STORY_FRAMEWORK.md"
      "project/ACCEPTANCE_CRITERIA.md"
      "project/README.md"
    )
  fi
fi

if [ "${#targets[@]}" -eq 0 ]; then
  echo "No targets to scan (project/meeting/ICLR2027/ is empty or missing)."
  echo "Pass --include-guidance to also scan project/STORY_FRAMEWORK.md etc."
  exit 0
fi

total_hits=0
hit_files=0

for f in "${targets[@]}"; do
  [ -f "$f" ] || continue

  # Filter: skip lines marked redline-allowed.
  raw=$(grep -nE "$PATTERNS" "$f" 2>/dev/null | grep -vF "$SKIP_MARKER" || true)

  if [ -n "$raw" ]; then
    count=$(echo "$raw" | wc -l | tr -d ' ')
    total_hits=$((total_hits + count))
    hit_files=$((hit_files + 1))
    echo "=== REDLINE HIT: $f ($count line$( [ "$count" -gt 1 ] && echo s)) ===" 1>&2
    echo "$raw" 1>&2
    echo "" 1>&2
  fi
done

if [ "$total_hits" -gt 0 ]; then
  echo "--------------------------------------------------------------" 1>&2
  echo "Total: $total_hits hit(s) across $hit_files file(s)." 1>&2
  echo "Reference: project/STORY_FRAMEWORK.md §R1-R10." 1>&2
  echo "To allow a specific line, append '  % redline-allowed' (tex)" 1>&2
  echo "or '<!-- redline-allowed -->' (md) at end of line." 1>&2
  exit 2
fi

echo "Red-line scan clean: $(echo "${targets[@]}" | wc -w) target(s) checked, 0 hits."
exit 0
