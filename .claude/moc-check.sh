#!/bin/bash
set -e
DFX_VER=0.24.3
V="$HOME/.cache/dfinity/versions/$DFX_VER"
MOC="$V/moc"
BASE="$V/base"
TARGET="/mnt/c/Users/Anthony/Documents/CafresoHQ/src/cafresoai_keys/main.mo"
echo "moc: $MOC"
echo "base: $BASE"
echo "target: $TARGET"
ls -la "$MOC" || echo "moc not found"
"$MOC" --check --package base "$BASE" "$TARGET"
echo "OK"
