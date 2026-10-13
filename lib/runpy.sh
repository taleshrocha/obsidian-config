#!/bin/sh
# Executa um script Python com o interpretador disponível (python3, python ou py -3).
# Usado pelos hooks de Git, que o Git roda via sh em Linux, macOS e Windows (Git for Windows).
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    exec python3 -X utf8 "$@"
elif command -v python >/dev/null 2>&1; then
    exec python -X utf8 "$@"
elif command -v py >/dev/null 2>&1; then
    exec py -3 -X utf8 "$@"
fi
echo "Python 3 não encontrado no PATH." >&2
exit 1
