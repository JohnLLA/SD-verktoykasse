#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Bygger, signerer og pakker verktøypakker for aarch64-apple-darwin, lokalt.
#   sidecar/build/bygg-mac.sh alle                       alle ti
#   sidecar/build/bygg-mac.sh subtitles,ocr              noen
#   sidecar/build/bygg-mac.sh alle --notariser [profil]  også notarisering (standard: jv-notary)
# Resultat: sidecar/build/out/dist/jv-<id>-<versjon>-aarch64-apple-darwin.tar.gz
set -euo pipefail
HER="$(cd "$(dirname "$0")" && pwd)"
JV="$(cd "$HER/../jv" && pwd)"
if [[ $# -lt 1 ]]; then
  echo "Bruk: $0 <id>[,<id>...]|alle [--notariser [profil]]" >&2; exit 1
fi
if [[ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]]; then
  echo "Mac-pakkene må bygges på en Mac med Apple Silicon." >&2; exit 1
fi
cd "$JV"
# Pakkene fra uv.lock; ingenting lastes ned hvis de ligger i uv-cachen (UV_OFFLINE=1).
uv sync --frozen --all-packages --quiet ${UV_OFFLINE:+--offline}
# PyInstaller med SHA-256 (samme versjon som på Windows); må komme etter uv sync, som fjerner alt utenfor uv.lock.
uv pip install --quiet --require-hashes -r "$HER/jvpack/mac/pyinstaller-krav.txt" ${UV_OFFLINE:+--offline}
exec uv run --frozen --all-packages --no-sync env PYTHONPATH="$HER" python -m jvpack mac "$@"
