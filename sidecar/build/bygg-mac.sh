#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Bygger, signerer og pakker verktøypakker for aarch64-apple-darwin.
#   sidecar/build/bygg-mac.sh subtitles,ocr
# Resultat: sidecar/build/out/dist/jv-<id>-<versjon>-aarch64-apple-darwin.tar.gz
set -euo pipefail
HER="$(cd "$(dirname "$0")" && pwd)"
JV="$(cd "$HER/../jv" && pwd)"
if [[ $# -ne 1 ]]; then
  echo "Bruk: $0 <id>[,<id>...]" >&2; exit 1
fi
if [[ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]]; then
  echo "Mac-pakkene må bygges på en Mac med Apple Silicon." >&2; exit 1
fi
cd "$JV"
# Pakkene fra uv.lock; ingenting lastes ned hvis de ligger i uv-cachen (UV_OFFLINE=1).
uv sync --frozen --all-packages --quiet ${UV_OFFLINE:+--offline}
exec uv run --frozen --all-packages --no-sync env PYTHONPATH="$HER" python -m jvpack mac "$1"
