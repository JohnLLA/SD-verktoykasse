# SPDX-License-Identifier: AGPL-3.0-or-later
"""macOS (aarch64-apple-darwin) packaging: Homebrew programs, Mach-O paths, signing.

Adapted from pakking/mac/builder in Verktoy2_0/journalistverktoy (the DMG
build). Differences: no tkinter shell, no DMG, no icon; the result is a
.tar.gz with jv-package.json instead.
"""

from pathlib import Path

HOMEBREW = Path("/opt/homebrew")
CELLAR = HOMEBREW / "Cellar"
