#!/usr/bin/env python3
"""Henter modellene som målingen trenger, og sjekker SHA-256 mot models.json.

Utviklerverktøy (ikke en del av appen). Bare standardbiblioteket.

    python3 -I tools/maling/hent_modeller.py --dir ~/lla-test/modeller
    python3 -I tools/maling/hent_modeller.py --dir ... --sizes small medium

Filene lagres som <id>.bin, samme navn som appen bruker. Ferdige filer med riktig
sum hoppes over. Nedlastingen kan gjenopptas (Range).
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download(url, dest, expected_bytes):
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(url)
    if have:
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req) as r:
        mode = "ab" if have and r.status == 206 else "wb"
        with open(part, mode) as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
    os.replace(part, dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--sizes", nargs="+", default=["small", "medium", "large"])
    ap.add_argument("--variants", nargs="+", default=["verbatim", "semantic", "main"])
    ap.add_argument("--quant", default="q5_0")
    a = ap.parse_args()
    os.makedirs(a.dir, exist_ok=True)
    cat = json.load(open(os.path.join(ROOT, "models.json"), encoding="utf-8"))
    bad = 0
    for m in cat["models"]:
        if m["size"] not in a.sizes or m["variant"] not in a.variants or m["quant"] != a.quant:
            continue
        dest = os.path.join(a.dir, m["id"] + ".bin")
        if os.path.exists(dest) and sha256_file(dest) == m["sha256"]:
            print("ok (fantes)", m["id"])
            continue
        print("laster ned", m["id"], f'{m["bytes"] / 1e6:.0f} MB', flush=True)
        download(m["url"], dest, m["bytes"])
        got = sha256_file(dest)
        if got != m["sha256"]:
            print("FEIL: SHA-256 stemmer ikke for", m["id"], file=sys.stderr)
            os.remove(dest)
            bad += 1
        else:
            print("ok", m["id"])
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
