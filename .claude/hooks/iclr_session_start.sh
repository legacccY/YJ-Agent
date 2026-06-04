#!/usr/bin/env bash
# SessionStart hook: brief reminder if cwd is YJ-Agent project.
# Output: stdout = additional context. Silent if not in project.

input=$(cat)
cwd=$(echo "$input" | grep -oE '"cwd"[[:space:]]*:[[:space:]]*"[^"]+"' | sed 's/.*"\([^"]*\)"$/\1/')
norm=$(echo "$cwd" | tr '\\' '/')

case "$norm" in
  */YJ-Agent*|*\YJ-Agent*) ;;
  *) exit 0 ;;
esac

cat <<'EOF'
[ICLR 2027 大项目 active] Read order if writing tex/数字: project/README.md → STORY_FRAMEWORK.md → ACCEPTANCE_CRITERIA.md → DATA_INVENTORY.md → PROJECT_LOG.md. BMVC SEALED. Opus 在 project/ 内默认开 caveman，用户说「关」才关。
EOF
exit 0
