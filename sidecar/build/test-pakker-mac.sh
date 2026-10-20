#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Kjører hvert verktøys egne Python-tester mot den pakkede binærfila (Mac).
#   sidecar/build/test-pakker-mac.sh alle
#   sidecar/build/test-pakker-mac.sh subtitles,ocr
# Pakkene pakkes ut på nytt fra out/dist i en ny mappe. Testene kjører i
# sandbox-exec uten nett og uten lesetilgang til Homebrew (pytest_packaged.py).
# Resultat per verktøy i out/test-oppsummering.txt.
set -euo pipefail
HER="$(cd "$(dirname "$0")" && pwd)"
JV="$(cd "$HER/../jv" && pwd)"
DIST="$HER/out/dist"
ALLE="compare,metadata,keyframes,loudness,subtitles,pdf-tables,datawrapper,ocr,redact,nynorsk"
ids="${1:-alle}"; [[ "$ids" == "alle" ]] && ids="$ALLE"
UT="$(mktemp -d "${TMPDIR:-/tmp}/jv-pakketest.XXXXXX")"
LOGG="$HER/out/test-logger"; rm -rf "$LOGG"; mkdir -p "$LOGG"
SUM="$HER/out/test-oppsummering.txt"
: > "$SUM"
feil=0
cd "$JV"
for id in ${ids//,/ }; do
  shopt -s nullglob
  arkiv=("$DIST"/jv-"$id"-*-aarch64-apple-darwin.tar.gz)
  shopt -u nullglob
  if [[ ${#arkiv[@]} -ne 1 ]]; then echo "[$id] fant ikke én pakke i $DIST" | tee -a "$SUM"; feil=1; continue; fi
  rot="$UT/$id"; mkdir -p "$rot"
  tar -xzf "${arkiv[0]}" -C "$rot"
  echo "[$id] tester mot $(basename "${arkiv[0]}")"
  set +e
  JV_PACKAGE_DIR="$rot" PYTHONPATH="$HER" uv run --frozen --all-packages --no-sync \
    pytest -q -p pytest_packaged "verktoy/$id" -p no:cacheprovider > "$LOGG/$id.log" 2>&1
  kode=$?
  set -e
  linje=$(grep -E "^(=+ )?[0-9]+ (passed|failed)|jv-pakke " "$LOGG/$id.log" | tr '\n' ' ')
  echo "[$id] kode $kode: $linje" | tee -a "$SUM"
  [[ $kode -eq 0 ]] || { feil=1; tail -30 "$LOGG/$id.log"; }
done
rm -rf "$UT"
exit $feil
