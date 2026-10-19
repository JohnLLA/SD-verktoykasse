# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools.json (the catalogue) and its minisign signature tools.json.sig.

    python -m jvpack katalog lag (--test-key | --key-file FIL) [--base-url URL] [--min-app 0.1.0]
        write out/dist/tools.json and tools.json.sig for the packages in out/dist
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

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from . import DIST, MANIFEST, TARGET_MAC, TARGET_WINDOWS, archive_name

RELEASE_REPO = "https://github.com/JohnLLA/lla-verktoykasse-releases"
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


def make_catalog(dist: Path, base_url: str | None, min_app: str, notes: dict[str, str]) -> dict:
    entries = []
    for archive in sorted(dist.glob("jv-*.tar.gz")) + sorted(dist.glob("jv-*.zip")):
        m = _manifest_of(archive)
        if archive.name != archive_name(m["id"], m["version"], m["target"]):
            raise SystemExit(f"{archive.name} passer ikke med jv-package.json i arkivet.")
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
    key, label = _key(argv)
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
    notes = {i: s.note for i, s in tools.SPECS.items()}
    data = make_catalog(DIST, base, min_app, notes)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    sig = write_signed(DIST / "tools.json", text.encode("utf-8"), key,
                       f"timestamp:{int(time.time())}\tfile:tools.json\t{label}")
    print(DIST / "tools.json", sig, f"({len(data['tools'])} linjer, {label})")
    return 0
