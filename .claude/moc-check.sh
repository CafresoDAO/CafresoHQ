#!/bin/bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
DFX_VER=0.24.3
V="$HOME/.cache/dfinity/versions/$DFX_VER"
MOC="$V/moc"
BASE="$V/base"
TARGET="$REPO_ROOT/src/cafresohq_keys/main.mo"
echo "moc: $MOC"
echo "base: $BASE"
echo "target: $TARGET"
ls -la "$MOC" || echo "moc not found"
"$MOC" --check --package base "$BASE" "$TARGET"
echo "OK"
