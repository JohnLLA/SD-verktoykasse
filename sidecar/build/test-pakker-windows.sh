#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Kjører hvert verktøys egne Python-tester mot den pakkede binærfila (Windows, Git Bash).
#   sidecar/build/test-pakker-windows.sh alle
#   sidecar/build/test-pakker-windows.sh subtitles,ocr
# Brukes av .github/workflows/jv-windows-pakker.yml. Pakkene pakkes ut på nytt fra
# out/dist. Før testene sperres utgående trafikk i Windows-brannmuren for hver .exe i
# pakken (krever administrator, som på GitHub-maskinene), og sperren prøves først på en
# kopi av curl.exe. Resultat per verktøy i out/test-oppsummering-windows.txt.
set -euo pipefail
HER="$(cd "$(dirname "$0")" && pwd)"
JV="$(cd "$HER/../jv" && pwd)"
DIST="$HER/out/dist"
ALLE="compare,metadata,keyframes,loudness,subtitles,pdf-tables,datawrapper,ocr,redact,nynorsk"
ids="${1:-alle}"; [[ "$ids" == "alle" ]] && ids="$ALLE"
UT="$(mktemp -d)"
LOGG="$HER/out/test-logger-windows"; rm -rf "$LOGG"; mkdir -p "$LOGG"
SUM="$HER/out/test-oppsummering-windows.txt"
: > "$SUM"
W() { cygpath -w "$1"; }

sperr() { # sperr <mappe>: blokker utgående trafikk for alle .exe under mappen
  powershell -NoProfile -NonInteractive -Command "
    \$ErrorActionPreference='Stop'
    Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True
    Get-ChildItem -LiteralPath '$(W "$1")' -Recurse -File -Filter *.exe | ForEach-Object {
      New-NetFirewallRule -DisplayName ('jv-test ' + \$_.FullName) -Direction Outbound -Action Block -Program \$_.FullName | Out-Null
    }" >/dev/null
}

# 1. Prøv sperren: curl.exe skal nå nettet, en sperret kopi skal ikke.
prove="$UT/sperreprove"; mkdir -p "$prove"
cp "$(cygpath -u "$SYSTEMROOT")/System32/curl.exe" "$prove/curl.exe"
"$prove/curl.exe" -s -o /dev/null --max-time 20 https://github.com || { echo "Ingen nettilgang på maskinen; sperren kan ikke prøves." | tee -a "$SUM"; exit 1; }
sperr "$prove"
if "$prove/curl.exe" -s -o /dev/null --max-time 20 https://github.com; then
  echo "Brannmursperren virker ikke (sperret curl.exe nådde github.com)." | tee -a "$SUM"; exit 1
fi
echo "Brannmursperren virker (sperret curl.exe nådde ikke github.com)." | tee -a "$SUM"

# Tester som ikke kan kjøres på Windows slik de er skrevet (med grunn i filen).
deselect=()
while IFS= read -r linje; do
  linje="${linje%%#*}"; linje="${linje%"${linje##*[![:space:]]}"}"
  [[ -n "$linje" ]] && deselect+=(--deselect "$linje")
done < "$HER/windows-ikke-portable-tester.txt"
echo "Valgt bort på Windows: $(( ${#deselect[@]} / 2 )) tester (windows-ikke-portable-tester.txt)." | tee -a "$SUM"

feil=0
cd "$JV"
for id in ${ids//,/ }; do
  shopt -s nullglob
  arkiv=("$DIST"/jv-"$id"-*-x86_64-pc-windows-msvc.zip)
  shopt -u nullglob
  if [[ ${#arkiv[@]} -ne 1 ]]; then echo "[$id] fant ikke én pakke i $DIST" | tee -a "$SUM"; feil=1; continue; fi
  rot="$UT/$id"; mkdir -p "$rot"
  uv run --frozen --all-packages --no-sync python -I -c \
    "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$(W "${arkiv[0]}")" "$(W "$rot")"
  sperr "$rot"
  echo "[$id] tester mot $(basename "${arkiv[0]}")"
  set +e
  JV_NETTSPERRE="brannmursperre for pakkens .exe-filer" JV_PACKAGE_DIR="$(W "$rot")" PYTHONPATH="$(W "$HER")" \
    uv run --frozen --all-packages --no-sync pytest -q -p pytest_packaged "verktoy/$id" -p no:cacheprovider "${deselect[@]}" \
    > "$LOGG/$id.log" 2>&1
  kode=$?
  set -e
  linje=$(grep -E "[0-9]+ (passed|failed)|jv-pakke " "$LOGG/$id.log" | tail -n 2 | tr '\n' ' ')
  echo "[$id] kode $kode: $linje" | tee -a "$SUM"
  [[ $kode -eq 0 ]] || { feil=1; tail -60 "$LOGG/$id.log"; }
done
powershell -NoProfile -NonInteractive -Command "Get-NetFirewallRule -DisplayName 'jv-test *' | Remove-NetFirewallRule" >/dev/null || true
exit $feil
