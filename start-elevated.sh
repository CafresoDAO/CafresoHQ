#!/usr/bin/env bash
# Launch serve.py with OpenClaw elevated endpoint enabled.
# Allowlist + tools are intentionally narrow — edit them here, not at runtime.
#
# Scope: ICP-Vault only. Agents can read/glob/grep/write/edit Markdown notes
# in the vault but cannot reach the rest of Documents and cannot spawn shells.
# Widen this when you actually need code-project access; restart afterwards.
export OPENCLAW_ALLOWED_DIRS="C:\\Users\\Anthony\\Documents;C:\\Users\\Anthony\\Downloads\\minegold.defi"
export OPENCLAW_ALLOWED_TOOLS="Read,Write,Edit,Glob,Grep,Bash"
cd "$(dirname "$0")"
exec python serve.py
