# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools.json (the catalogue) and its minisign signature tools.json.sig.

    python -m jvpack katalog lag (--test-key | --key-file FIL | --usignert)
                                 [--dist MAPPE]... [--ut MAPPE] [--base-url URL] [--min-app 0.1.0]
        write tools.json (and tools.json.sig) for the packages in out/dist, or in
        every --dist folder (Mac .tar.gz and Windows .zip together). --usignert
        writes only tools.json, for John Inge to sign with minisign
        (`minisign -S -s katalog.key -m tools.json -x tools.json.sig`).
        --behold FIL: keep the lines of an existing, signed catalogue (FIL and
        FIL.sig, checked against the app's key in catalog.rs) for every tool and
        platform that has no package in the --dist folders. That is how Windows
        lines are added without the Mac packages at hand.
    python -m jvpack katalog signer <fil> (--test-key | --key-file FIL)
        write <fil>.sig
    python -m jvpack katalog nokkel (--test-key | --key-file FIL)
        print the public key (the line the app needs)
    python -m jvpack katalog nokkel lag [--key-file FIL]
        make a local BETA key (default ~/.lla-verktoykasse/katalog-beta.key),
        outside the repo and never committed

The signature is minisign's own format (prehashed «ED»: Ed25519 over
BLAKE2b-512 of the file, plus a signed trusted comment), so the app checks it
with the minisign-verify crate, and the real catalogue can later be signed with
the minisign tool itself (`minisign -S -m tools.json`).

--test-key: a fixed TEST key derived from a public string. It is not a secret
and must never sign a real catalogue; the app only trusts it in tests.

--key-file: a local beta key (32 random bytes, file mode 600). The app trusts
it only when it is built with JV_CATALOG_PUBLIC_KEY=<public key> (see
src-tauri/src/tools/jv/catalog.rs). The real key is made by John Inge with
`minisign -G`; its public half goes into PUBLIC_KEY in catalog.rs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tarfile
import time
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from . import DIST, MANIFEST, TARGET_MAC, TARGET_WINDOWS, archive_name

RELEASE_REPO = "https://github.com/JohnLLA/sd-verktoy-releases"
TEST_SEED_TEXT = b"lla-verktoykasse: TESTNOKKEL for verktoykatalogen. Ikke hemmelig. Aldri i produksjon."
CATALOG_SCHEMA = 1


class Key:
    def __init__(self, seed: bytes, key_id: bytes):
        self.sk = Ed25519PrivateKey.from_private_bytes(seed)
        self.pk = self.sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = key_id  # 8 bytes, little endian as in minisign

    @property
    def key_id_hex(self) -> str:
        return self.key_id[::-1].hex().upper()

    def public_key_file(self) -> str:
        b64 = base64.b64encode(b"Ed" + self.key_id + self.pk).decode()
        return f"untrusted comment: minisign public key {self.key_id_hex} (TESTNØKKEL)\n{b64}\n"

    def public_key_b64(self) -> str:
        return base64.b64encode(b"Ed" + self.key_id + self.pk).decode()

    def sign(self, data: bytes, trusted_comment: str) -> str:
        digest = hashlib.blake2b(data, digest_size=64).digest()
        sig = self.sk.sign(digest)
        global_sig = self.sk.sign(sig + trusted_comment.encode("utf-8"))
        return (
            f"untrusted comment: signature from minisign secret key {self.key_id_hex}\n"
            f"{base64.b64encode(b'ED' + self.key_id + sig).decode()}\n"
            f"trusted comment: {trusted_comment}\n"
            f"{base64.b64encode(global_sig).decode()}\n"
        )


def app_public_key() -> str:
    """PUBLIC_KEY from src-tauri/src/tools/jv/catalog.rs (the key the app trusts)."""
    import re

    from . import SIDECAR

    rs = (SIDECAR.parent / "src-tauri" / "src" / "tools" / "jv" / "catalog.rs").read_text(encoding="utf-8")
    m = re.search(r'pub const PUBLIC_KEY: &str = "([^"]*)";', rs)
    if not m or not m.group(1):
        raise SystemExit("Fant ikke PUBLIC_KEY i catalog.rs.")
    return m.group(1)


def verify(data: bytes, sig_text: str, public_key_b64: str) -> None:
    """Check a minisign signature (prehashed «ED» only, as the app). SystemExit on failure."""
    pk = base64.b64decode(public_key_b64)
    lines = [ln for ln in sig_text.splitlines() if ln.strip()]
    try:
        sig = base64.b64decode(lines[1])
        trusted = lines[2].removeprefix("trusted comment: ")
        global_sig = base64.b64decode(lines[3])
        if pk[:2] != b"Ed" or sig[:2] != b"ED" or sig[2:10] != pk[2:10]:
            raise ValueError
        key = Ed25519PublicKey.from_public_bytes(pk[10:42])
        key.verify(sig[10:74], hashlib.blake2b(data, digest_size=64).digest())
        key.verify(global_sig, sig[10:74] + trusted.encode("utf-8"))
    except (IndexError, ValueError, InvalidSignature):
        raise SystemExit("Signaturen på katalogen stemmer ikke med nøkkelen. Ingenting er skrevet.") from None


def test_key() -> Key:
    h = hashlib.sha256(TEST_SEED_TEXT).digest()
    return Key(h, hashlib.sha256(h).digest()[:8])


DEFAULT_BETA_KEY = Path.home() / ".lla-verktoykasse" / "katalog-beta.key"


def make_beta_key(path: Path) -> Key:
    """A new local beta key. Refuses to write inside a git work tree."""
    path = path.expanduser().resolve()
    for parent in [path.parent, *path.parent.parents]:
        if (parent / ".git").exists():
            raise SystemExit(f"Nøkkelen skal ikke ligge i et git-repo ({parent}). Velg en sti utenfor.")
    if path.exists():
        raise SystemExit(f"{path} finnes fra før. Slett den selv hvis du vil lage en ny.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    seed, key_id = secrets.token_bytes(32), secrets.token_bytes(8)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"type": "lla-verktoykasse beta-katalognøkkel (Ed25519)",
                   "seed": base64.b64encode(seed).decode(), "key_id": base64.b64encode(key_id).decode()}, fh)
    return Key(seed, key_id)


def load_key_file(path: Path) -> Key:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    return Key(base64.b64decode(data["seed"]), base64.b64decode(data["key_id"]))


def _manifest_of(archive: Path) -> dict:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            return json.loads(z.read(MANIFEST).decode("utf-8"))
    with tarfile.open(archive, "r:gz") as tar:
        member = tar.getmember(MANIFEST)
        fh = tar.extractfile(member)
        assert fh is not None
        return json.loads(fh.read().decode("utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _archives(dists: list[Path]) -> list[Path]:
    out = []
    for dist in dists:
        out += sorted(dist.glob("jv-*.tar.gz")) + sorted(dist.glob("jv-*.zip"))
    return out


def make_catalog(dist: Path | list[Path], base_url: str | None, min_app: str, notes: dict[str, str],
                 keep: list[dict] | None = None) -> dict:
    """`keep`: lines from an existing (checked) catalogue, used for every
    (id, target) that has no package in `dist`."""
    dists = dist if isinstance(dist, list) else [dist]
    entries = []
    seen: set[tuple[str, str]] = set()
    for archive in _archives(dists):
        m = _manifest_of(archive)
        if archive.name != archive_name(m["id"], m["version"], m["target"]):
            raise SystemExit(f"{archive.name} passer ikke med jv-package.json i arkivet.")
        if (m["id"], m["target"]) in seen:
            raise SystemExit(f"To pakker for {m['id']} ({m['target']}). Bare én versjon per plattform kan stå i katalogen.")
        seen.add((m["id"], m["target"]))
        tag = f"jv-{m['id']}-v{m['version']}"
        url = f"{base_url.rstrip('/')}/{archive.name}" if base_url else f"{RELEASE_REPO}/releases/download/{tag}/{archive.name}"
        entries.append({
            "id": m["id"],
            "name": m["name"],
            "version": m["version"],
            "target": m["target"],
            "url": url,
            "bytes": archive.stat().st_size,
            "sha256": _sha256(archive),
            "min_app_version": min_app,
            "min_os": m.get("min_os"),
            "notes": notes.get(m["id"], ""),
        })
    for old in keep or []:
        if (old["id"], old["target"]) not in seen:
            seen.add((old["id"], old["target"]))
            entries.append(old)
    entries.sort(key=lambda e: (e["id"], e["target"]))
    return {"schema": CATALOG_SCHEMA, "targets": [TARGET_MAC, TARGET_WINDOWS], "tools": entries}


def write_signed(path: Path, data: bytes, key: Key, comment: str) -> Path:
    path.write_bytes(data)
    sig = path.with_name(path.name + ".sig")
    sig.write_text(key.sign(data, comment), encoding="utf-8")
    return sig


def _key(argv: list[str]) -> tuple[Key, str]:
    if "--test-key" in argv:
        return test_key(), "TESTNØKKEL"
    if "--key-file" in argv:
        return load_key_file(Path(argv[argv.index("--key-file") + 1])), "BETANØKKEL"
    raise SystemExit("Velg --test-key eller --key-file <fil> (lag en med «katalog nokkel lag»).")


def main(argv: list[str]) -> int:
    from . import tools

    if argv[:2] == ["nokkel", "lag"]:
        path = Path(argv[argv.index("--key-file") + 1]) if "--key-file" in argv else DEFAULT_BETA_KEY
        key = make_beta_key(path)
        print(f"Ny betanøkkel: {path.expanduser()} (ikke del den, ikke legg den i git)")
        print(f"Offentlig nøkkel (bygg appen med JV_CATALOG_PUBLIC_KEY=...): {key.public_key_b64()}")
        return 0
    if not argv or argv[0] not in ("nokkel", "signer", "lag"):
        print(__doc__)
        return 1
    unsigned = argv[0] == "lag" and "--usignert" in argv
    key, label = (None, "USIGNERT") if unsigned else _key(argv)
    if argv[0] == "nokkel":
        print(key.public_key_b64())
        return 0
    if argv[0] == "signer":
        target = Path(argv[1])
        sig = write_signed(target, target.read_bytes(), key,
                           f"timestamp:{int(time.time())}\tfile:{target.name}\t{label}")
        print(sig)
        return 0
    base = argv[argv.index("--base-url") + 1] if "--base-url" in argv else None
    min_app = argv[argv.index("--min-app") + 1] if "--min-app" in argv else "0.1.0"
    dists = [Path(argv[i + 1]) for i, a in enumerate(argv) if a == "--dist" and i + 1 < len(argv)] or [DIST]
    out_dir = Path(argv[argv.index("--ut") + 1]) if "--ut" in argv else dists[0]
    notes = {i: s.note for i, s in tools.SPECS.items()}
    keep = None
    if "--behold" in argv:
        old_path = Path(argv[argv.index("--behold") + 1])
        old_bytes = old_path.read_bytes()
        pub = test_key().public_key_b64() if "--test-key" in argv else app_public_key()
        verify(old_bytes, old_path.with_name(old_path.name + ".sig").read_text(encoding="utf-8"), pub)
        keep = json.loads(old_bytes.decode("utf-8"))["tools"]
        print(f"Beholder linjer fra {old_path} (signaturen stemmer): {len(keep)}")
    data = make_catalog(dists, base, min_app, notes, keep)
    if not data["tools"] or (keep is not None and len(data["tools"]) == len(keep)):
        raise SystemExit(f"Fant ingen pakker i {', '.join(map(str, dists))}. Ingenting er skrevet.")
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_target: dict[str, int] = {}
    for e in data["tools"]:
        per_target[e["target"]] = per_target.get(e["target"], 0) + 1
    counts = ", ".join(f"{t}: {n}" for t, n in sorted(per_target.items()))
    if key is None:
        path = out_dir / "tools.json"
        path.write_bytes(text.encode("utf-8"))
        stale = out_dir / "tools.json.sig"
        if stale.exists():
            stale.unlink()  # never leave a signature that belongs to another catalogue
        print(path, f"({len(data['tools'])} linjer: {counts}; USIGNERT)")
        print(f"Signer med: minisign -S -s <katalog.key> -m {path} -x {path}.sig")
        return 0
    sig = write_signed(out_dir / "tools.json", text.encode("utf-8"), key,
                       f"timestamp:{int(time.time())}\tfile:tools.json\t{label}")
    print(out_dir / "tools.json", sig, f"({len(data['tools'])} linjer: {counts}; {label})")
    return 0
