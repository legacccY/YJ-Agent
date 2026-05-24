#!/usr/bin/env bash
# PreToolUse hook: block edits to sealed BMVC dir.
# Input: JSON on stdin {tool_name, tool_input:{file_path,...}}
# Output: exit 2 + stderr = block tool. Silent on pass.

input=$(cat)
tool=$(echo "$input" | grep -oE '"tool_name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/')

case "$tool" in
  Edit|Write|NotebookEdit|MultiEdit) ;;
  *) exit 0 ;;
esac

path=$(echo "$input" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/')

# Normalize separators for matching
norm=$(echo "$path" | tr '\\' '/')

case "$norm" in
  *project/meeting/BMVC/*|*project\\meeting\\BMVC\\*)
    # Allow only rebuttal/ and camera_ready/ subpaths
    case "$norm" in
      *meeting/BMVC/rebuttal/*|*meeting/BMVC/camera_ready/*) exit 0 ;;
    esac
    echo "BMVC SEALED 2026-05-24. Edit blocked: $path. Use meeting/ICLR2027/ for new work; meeting/BMVC/rebuttal/ for rebuttal." 1>&2
    exit 2
    ;;
esac

exit 0
