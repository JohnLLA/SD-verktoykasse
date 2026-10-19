#!/bin/sh
# Copies the step-6 agent into .claude/agents/ (Claude Code reads agents from there).
cd "$(dirname "$0")/.." && mkdir -p .claude/agents && cp oppsett/claude/agents/*.md .claude/agents/ && echo "sidecar-bygger er lagt i .claude/agents/"
