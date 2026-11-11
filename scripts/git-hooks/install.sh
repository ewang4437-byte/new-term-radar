#!/bin/sh
# Copies the privacy hooks into this clone's .git/hooks (shared by all its worktrees).
d=$(git rev-parse --git-common-dir)/hooks
cp "$(dirname "$0")/pre-commit" "$(dirname "$0")/pre-push" "$d/" && chmod +x "$d/pre-commit" "$d/pre-push" && echo "installed in $d"
