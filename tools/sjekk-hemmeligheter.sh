#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Stopper bygget hvis en fil som aldri skal i repoet er med (spesifikasjon-journalistverktoy.md):
# signerings- og API-nøkler (.p8, .p12, .pem, .env), notarisering/ og .claude/ eller oppsett/
# fra Verktoy2_0 under sidecar/, byggmapper fra pakking/, og private nøkler i filinnhold.
# Sjekker filene git kjenner (sporet + nye som ikke er ignorert).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
files=$( { git ls-files; git ls-files --others --exclude-standard; } | sort -u)
bad_names=$(printf '%s\n' "$files" | grep -E \
  -e '\.(p8|p12|pem|pfx|key)$' \
  -e '(^|/)\.env($|\.)' -e '\.env$' \
  -e '(^|/)notarisering/' \
  -e '^sidecar/(.*/)?\.claude/' -e '^sidecar/(.*/)?oppsett/' \
  -e '(^|/)pakking/[^/]+/(build|dist)/' \
  -e '(^|/)AuthKey_[A-Z0-9]+' || true)
bad_content=$(printf '%s\n' "$files" | while IFS= read -r f; do
  [ -f "$f" ] || continue
  [ "$f" = tools/sjekk-hemmeligheter.sh ] && continue
  if grep -IlE -e '-----BEGIN ([A-Z]+ )?PRIVATE KEY-----' -e 'minisign encrypted secret key' "$f" >/dev/null 2>&1; then
    echo "$f"
  fi
done)
if [ -n "$bad_names$bad_content" ]; then
  echo "Filer som ikke skal i repoet:" >&2
  printf '%s\n' $bad_names $bad_content >&2
  exit 1
fi
echo "Ingen hemmeligheter eller sperrede mapper funnet."
