#!/bin/sh
# Atalho para Linux e macOS. Toda a lógica está em install.py.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec sh "$DIR/lib/runpy.sh" "$DIR/install.py" "$@"
