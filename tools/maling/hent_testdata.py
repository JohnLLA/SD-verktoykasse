#!/usr/bin/env python3
"""Henter og bygger testlyden for steg 3, og sjekker den mot SHA-256.

Utviklerverktøy (ikke en del av appen). Bare standardbiblioteket; kjør med -I:

    # Lag lyden på nytt (gjør det som trengs, sjekker alt mot testdata/klipp.json):
    python3 -I tools/maling/hent_testdata.py hent

    # Bare sjekk at lyden som ligger i testdata/lyd/ er den riktige:
    python3 -I tools/maling/hent_testdata.py sjekk

    # Vedlikehold (kjørt én gang av den som setter opp testsettet):
    python3 -I tools/maling/hent_testdata.py velg

Kildene (NPSC, FLEURS, NbAiLab-eksemplene) lastes ned til en bufferkatalog
(`--cache`, standard ~/lla-test/kilder) og sjekkes mot SHA-256 fra
`testdata/klipp.json`. Klippene (16 kHz mono WAV) bygges med appens egen
dekoder, via eksempelprogrammet `maal decode`:

    cd src-tauri && cargo build --release --features maling --example maal

Forringede varianter (telefon, rom med ekko, kafé, bil) lages av de rene
klippene med fast frø i ren Python. De er simulert, ikke ekte opptak.

SHA-256 på kildene er strengt (avvik stopper). SHA-256 på de ferdige klippene
sjekkes også, men et avvik gir bare en advarsel (exit 2 med --streng): dekoder
og FFT kan gi avvik på siste bit mellom CPU-arkitekturer.
"""
import argparse
import array
import hashlib
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import wave

HER = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HER))
TESTDATA = os.path.join(ROOT, "testdata")
KLIPP_JSON = os.path.join(TESTDATA, "klipp.json")
FASIT_DIR = os.path.join(TESTDATA, "fasit")
LYD_DIR = os.path.join(TESTDATA, "lyd")

NPSC_REV = "e906435cc445e38961d86f3ebf53a7b38603b903"
FLEURS_REV = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
NPSC_BASE = f"https://huggingface.co/datasets/NbAiLab/NPSC/resolve/{NPSC_REV}/data"
FLEURS_BASE = f"https://huggingface.co/datasets/google/fleurs/resolve/{FLEURS_REV}/data/nb_no"
NB_WHISPER_AUDIO = "https://github.com/NbAiLab/nb-whisper/raw/main/audio"

# ---------------------------------------------------------------------------
# Valg av klipp (brukes bare av `velg`). (id, split, dato, speaker_id, språk, mål i sekunder)
# ---------------------------------------------------------------------------
RENE = [
    ("nb-1", "test", "20171219", 3, "nb", 180),
    ("nb-2", "test", "20170207", 26, "nb", 120),
    ("nb-3", "eval", "20180611", 132, "nb", 120),
    ("nb-4", "eval", "20180109", 289, "nb", 120),
    ("nn-1", "eval", "20170209", 36, "nn", 180),
    ("nn-2", "test", "20171219", 92, "nn", 120),
    ("nn-3", "eval", "20180109", 253, "nn", 120),
    ("nn-4", "eval", "20180611", 271, "nn", 120),
]
# Forringede varianter: (id, base, effekt, snr_db)
FORRINGET = [
    ("nb-1-telefon", "nb-1", "telefon", None),
    ("nb-1-ekko", "nb-1", "ekko", None),
    ("nb-1-kafe", "nb-1", "kafe", 8),
    ("nb-1-bil", "nb-1", "bil", 5),
    ("nn-1-telefon", "nn-1", "telefon", None),
    ("nn-1-kafe", "nn-1", "kafe", 8),
]
# Kafé-støy: tale fra fire andre talere i samme møte, lagt oppå hverandre.
BABBLE = {"split": "test", "dato": "20171122", "talere": 4, "sekunder": 150}
LANG = {"id": "lang-nb-30", "split": "test", "dato": "20171122", "sekunder": 1800}
FLEURS_ANTALL = {"MALE": 10, "FEMALE": 15}


def sha256_fil(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def last_ned(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    with urllib.request.urlopen(url) as r, open(part, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(part, dest)


def hent_kilde(k, cache, pin=False):
    """Sørger for at kilden finnes i bufferet og har riktig SHA-256."""
    dest = os.path.join(cache, k["fil"])
    if not os.path.exists(dest):
        print("laster ned", k["id"], flush=True)
        last_ned(k["url"], dest)
    sha = sha256_fil(dest)
    if pin:
        k["sha256"] = sha
        k["bytes"] = os.path.getsize(dest)
    elif sha != k["sha256"]:
        sys.exit(f"FEIL: SHA-256 stemmer ikke for kilden {k['id']} (forventet {k['sha256'][:12]}..., fikk {sha[:12]}...)")
    return dest


# ---------------------------------------------------------------------------
# NPSC-hjelpere
# ---------------------------------------------------------------------------
def les_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def npsc_kilder(split, dato):
    return [
        {"id": f"npsc-{split}-{dato}-json", "url": f"{NPSC_BASE}/{split}/{dato}.json",
         "fil": f"npsc/{split}/{dato}.json", "lisens": "CC0-1.0"},
        {"id": f"npsc-{split}-{dato}-16k-mp3", "url": f"{NPSC_BASE}/{split}/{dato}_16K_mp3.tar.gz",
         "fil": f"npsc/{split}/{dato}_16K_mp3.tar.gz", "lisens": "CC0-1.0"},
    ]


def kjoringer(rader, sprak):
    """Sammenhengende løp: samme taler og språk, sammenhengende setningsnummer, ingen <INAUDIBLE>."""
    kode = {"nb": "nb-NO", "nn": "nn-NO"}[sprak]
    ut, cur = [], []
    for r in rader:
        ok = r["sentence_language_code"] == kode and "<INAUDIBLE>" not in r["sentence_text"]
        if cur and (not ok or r["speaker_id"] != cur[-1]["speaker_id"]
                    or r["sentence_order"] != cur[-1]["sentence_order"] + 1):
            ut.append(cur)
            cur = []
        if ok:
            cur.append(r)
    if cur:
        ut.append(cur)
    return ut


def varighet(rader):
    return sum(r["end_time"] - r["start_time"] for r in rader) / 1000


def ta_til(rader, sekunder):
    ut = []
    for r in rader:
        ut.append(r)
        if varighet(ut) >= sekunder:
            break
    return ut


def fasit_fra_npsc(rader):
    return [{"id": r["sentence_id"], "lydrett": r["sentence_text"], "skriftlig": r["normsentence_text"],
             "maskinoversatt": r["transsentence_text"]} for r in rader]


def mp3_navn(r):
    return r["path"] + ".mp3"


# ---------------------------------------------------------------------------
# velg: lager klipp.json og fasit/*.json
# ---------------------------------------------------------------------------
def kommando_velg(a):
    cache = os.path.expanduser(a.cache)
    kilder, klipp = {}, []

    def kilde(k):
        kilder.setdefault(k["id"], k)
        hent_kilde(kilder[k["id"]], cache, pin=True)

    def json_for(split, dato):
        ks = npsc_kilder(split, dato)
        for k in ks:
            kilde(k)
        return les_jsonl(os.path.join(cache, ks[0]["fil"])), [k["id"] for k in ks]

    os.makedirs(FASIT_DIR, exist_ok=True)
    for kid, split, dato, spk, sprak, mal in RENE:
        rader, ks = json_for(split, dato)
        lop = [l for l in kjoringer(rader, sprak) if l[0]["speaker_id"] == spk]
        best = max(lop, key=varighet)
        valgt = ta_til(best, mal)
        fasit = {"id": kid, "kilde": "NPSC", "sprak": sprak, "setninger": fasit_fra_npsc(valgt)}
        json.dump(fasit, open(os.path.join(FASIT_DIR, kid + ".json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        klipp.append({
            "id": kid, "type": "npsc", "sprak": sprak, "split": split, "dato": dato,
            "speaker_id": spk, "setning_ider": [r["sentence_id"] for r in valgt],
            "mp3": [mp3_navn(r) for r in valgt], "gap_ms": 300, "kilder": ks,
            "fasit": kid, "lisens": "CC0-1.0",
            "beskrivelse": f"Stortinget, taler {spk}, møte {dato}, {len(valgt)} sammenhengende setninger",
        })
    for kid, base, effekt, snr in FORRINGET:
        b = next(k for k in klipp if k["id"] == base)
        e = {"id": kid, "type": "forringet", "base": base, "effekt": effekt, "sprak": b["sprak"],
             "fasit": b["fasit"], "lisens": "CC0-1.0 (avledet)",
             "beskrivelse": {"telefon": "telefonkvalitet: 300-3400 Hz, 8 kHz, mu-lov 8 bit",
                             "ekko": "rom med mye etterklang (Schroeder-romklang, ca. 1 s)",
                             "kafe": f"kafé: fire andre talere som babbel, SNR {snr} dB",
                             "bil": f"bil: lavfrekvent rumling, SNR {snr} dB"}[effekt]}
        if snr is not None:
            e["snr_db"] = snr
        if effekt == "kafe":
            e["stoy"] = "babble"
        klipp.append(e)

    # Babbel-kilde: fire ulike talere fra samme møte
    rader, ks = json_for(BABBLE["split"], BABBLE["dato"])
    per_taler = {}
    for l in kjoringer(rader, "nb"):
        if varighet(l) >= BABBLE["sekunder"]:
            per_taler.setdefault(l[0]["speaker_id"], l)
    talere = sorted(per_taler)[: BABBLE["talere"]]
    klipp.append({
        "id": "stoy-babble", "type": "stoykilde", "kun_stoy": True, "kilder": ks, "gap_ms": 0,
        "dato": BABBLE["dato"], "split": BABBLE["split"],
        "deler": [{"speaker_id": t, "mp3": [mp3_navn(r) for r in ta_til(per_taler[t], BABBLE["sekunder"])]}
                  for t in talere],
        "lisens": "CC0-1.0", "beskrivelse": "Babbel til kafé-klippene (brukes ikke som eget klipp)"})

    # Lang fil: 30 min sammenhengende bokmål fra ett møte
    rader, ks = json_for(LANG["split"], LANG["dato"])
    valgt = []
    for r in rader:
        if r["sentence_language_code"] == "nb-NO" and "<INAUDIBLE>" not in r["sentence_text"]:
            valgt.append(r)
            if varighet(valgt) >= LANG["sekunder"]:
                break
    json.dump({"id": LANG["id"], "kilde": "NPSC", "sprak": "nb", "setninger": fasit_fra_npsc(valgt)},
              open(os.path.join(FASIT_DIR, LANG["id"] + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    klipp.append({"id": LANG["id"], "type": "npsc", "sprak": "nb", "split": LANG["split"], "dato": LANG["dato"],
                  "setning_ider": [r["sentence_id"] for r in valgt], "mp3": [mp3_navn(r) for r in valgt],
                  "gap_ms": 300, "kilder": ks, "fasit": LANG["id"], "lisens": "CC0-1.0", "lang": True,
                  "beskrivelse": f"Stortinget, møte {LANG['dato']}, {len(valgt)} setninger fra flere talere"})

    # FLEURS
    ks = [{"id": "fleurs-nb-test-tsv", "url": f"{FLEURS_BASE}/test.tsv", "fil": "fleurs/test.tsv", "lisens": "CC-BY-4.0"},
          {"id": "fleurs-nb-test-tar", "url": f"{FLEURS_BASE}/audio/test.tar.gz", "fil": "fleurs/test.tar.gz",
           "lisens": "CC-BY-4.0"}]
    for k in ks:
        kilde(k)
    import csv
    rader = list(csv.reader(open(os.path.join(cache, "fleurs/test.tsv"), encoding="utf-8"), delimiter="\t"))
    telt = {"MALE": 0, "FEMALE": 0}
    valgt = []
    for r in rader:
        g = r[-1]
        if g in telt and telt[g] < FLEURS_ANTALL[g]:
            telt[g] += 1
            valgt.append(r)
    json.dump({"id": "fleurs-nb", "kilde": "FLEURS nb_no test", "sprak": "nb",
               "setninger": [{"id": r[1], "lydrett": r[3], "skriftlig": r[2], "kjonn": r[-1]} for r in valgt]},
              open(os.path.join(FASIT_DIR, "fleurs-nb.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    klipp.append({"id": "fleurs-nb", "type": "fleurs", "sprak": "nb", "wav": [f"test/{r[1]}" for r in valgt],
                  "gap_ms": 500, "kilder": [k["id"] for k in ks], "fasit": "fleurs-nb", "lisens": "CC-BY-4.0",
                  "beskrivelse": f"FLEURS nb_no, {len(valgt)} opplest setninger fra {telt['MALE']} menn og {telt['FEMALE']} kvinner"})

    # NbAiLabs egne eksempler (bare fart og et skjønnsmessig sammenlikningsgrunnlag; ingen fasit)
    for navn, beskr in (("king", "Kongens nyttårstale (utdrag), 85 s. Offentlig referanse, ingen fasit"),
                        ("knuthamsun", "Knut Hamsun, opplesning, 23 min. Brukes til fart, ingen fasit")):
        k = {"id": f"nbwhisper-{navn}", "url": f"{NB_WHISPER_AUDIO}/{navn}.mp3", "fil": f"nb-whisper/{navn}.mp3",
             "lisens": "Apache-2.0 (NbAiLab/nb-whisper-repoet); se README"}
        kilde(k)
        klipp.append({"id": navn, "type": "fil", "sprak": "nb", "kilder": [k["id"]], "ingen_fasit": True,
                      "lisens": k["lisens"], "beskrivelse": beskr})

    doc = {"npsc_revision": NPSC_REV, "fleurs_revision": FLEURS_REV,
           "kilder": list(kilder.values()), "klipp": klipp}
    json.dump(doc, open(KLIPP_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("skrev", KLIPP_JSON)


# ---------------------------------------------------------------------------
# Lyd: WAV-hjelpere og forringelser (ren Python, fast frø)
# ---------------------------------------------------------------------------
def les_wav(path):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == 16000, path
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    if sys.byteorder == "big":
        a.byteswap()
    return a


def skriv_wav(path, samples):
    a = array.array("h", samples)
    if sys.byteorder == "big":
        a.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(a.tobytes())


def rms(x):
    return math.sqrt(sum(v * v for v in x) / max(1, len(x)))


def biquad(x, kind, f0, fs=16000, q=0.7071):
    w0 = 2 * math.pi * f0 / fs
    c, al = math.cos(w0), math.sin(w0) / (2 * q)
    if kind == "lp":
        b0, b1, b2 = (1 - c) / 2, 1 - c, (1 - c) / 2
    else:
        b0, b1, b2 = (1 + c) / 2, -(1 + c), (1 + c) / 2
    a0, a1, a2 = 1 + al, -2 * c, 1 - al
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    x1 = x2 = y1 = y2 = 0.0
    out = [0.0] * len(x)
    for i, v in enumerate(x):
        y = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, v
        y2, y1 = y1, y
        out[i] = y
    return out


def til_int16(x, topp=0.95):
    m = max((abs(v) for v in x), default=1.0)
    g = min(1.0, topp * 32767 / m) if m > 0 else 1.0
    return array.array("h", (int(round(max(-32768, min(32767, v * g)))) for v in x))


def mulov(v, mu=255.0):
    s = -1.0 if v < 0 else 1.0
    y = s * math.log1p(mu * abs(v)) / math.log1p(mu)
    q = round(y * 127) / 127
    s = -1.0 if q < 0 else 1.0
    return s * ((1 + mu) ** abs(q) - 1) / mu


def effekt_telefon(x):
    f = [float(v) for v in x]
    f = biquad(biquad(f, "hp", 300), "hp", 300)
    f = biquad(biquad(f, "lp", 3400), "lp", 3400)
    ned = f[::2]  # 8 kHz
    ned = [mulov(max(-1.0, min(1.0, v / 32768))) * 32768 for v in ned]
    opp = []
    for i, v in enumerate(ned):
        nxt = ned[i + 1] if i + 1 < len(ned) else v
        opp.append(v)
        opp.append((v + nxt) / 2)
    return til_int16(opp)


def effekt_ekko(x):
    fs = 16000
    f = [float(v) for v in x]
    n = len(f)
    wet = [0.0] * n
    for d in (1620, 1724, 1852, 1968):
        g = 10 ** (-3 * d / (1.0 * fs))  # RT60 = 1,0 s
        buf = [0.0] * d
        k = 0
        for i in range(n):
            y = f[i] + g * buf[k]
            buf[k] = y
            wet[i] += y
            k += 1
            if k == d:
                k = 0
    for d in (338, 245):
        g = 0.5
        buf = [0.0] * d
        k = 0
        out = [0.0] * n
        for i in range(n):
            bo = buf[k]
            v = wet[i] + g * bo
            buf[k] = v
            out[i] = bo - g * v
            k += 1
            if k == d:
                k = 0
        wet = out
    rw, rd = rms(wet), rms(f)
    s = 0.8 * rd / rw if rw > 0 else 0.0
    return til_int16([a + s * b for a, b in zip(f, wet)])


def mix_snr(tale, stoy, snr_db):
    f = [float(v) for v in tale]
    n = len(f)
    if len(stoy) < n:
        stoy = (list(stoy) * (n // max(1, len(stoy)) + 1))
    stoy = [float(v) for v in stoy[:n]]
    rs, rn = rms(f), rms(stoy)
    g = rs / (rn * 10 ** (snr_db / 20)) if rn > 0 else 0.0
    return til_int16([a + g * b for a, b in zip(f, stoy)])


def stoy_bil(n, seed=20240601):
    rnd = random.Random(seed)
    x = [rnd.gauss(0, 1) for _ in range(n)]
    x = biquad(biquad(x, "lp", 400), "lp", 400)
    r = rms(x)
    return [v + 0.3 * r * math.sin(2 * math.pi * 100 * i / 16000) for i, v in enumerate(x)]


def stoy_babble(wavs):
    """Legger talestrømmene oppå hverandre (alle like høye)."""
    n = min(len(w) for w in wavs)
    ut = [0.0] * n
    for w in wavs:
        r = rms(w[:n]) or 1.0
        for i in range(n):
            ut[i] += w[i] / r
    return ut


# ---------------------------------------------------------------------------
# hent: bygger lyden
# ---------------------------------------------------------------------------
def finn_maal(arg):
    if arg:
        return arg
    exe = "maal.exe" if os.name == "nt" else "maal"
    return os.path.join(ROOT, "src-tauri", "target", "release", "examples", exe)


def dekod(maal, mp3s, gap_ms, ut):
    cmd = [maal, "decode", "--gap-ms", str(gap_ms), "--out", ut]
    for m in mp3s:
        cmd += ["--in", m]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("maal decode feilet: " + r.stderr.strip()[-300:])


def pakk_ut_tar(tar_path, navn, mappe):
    ut = []
    with tarfile.open(tar_path, "r:gz") as t:
        mem = {m.name: m for m in t.getmembers() if m.isfile()}
        for n in navn:
            m = mem.get(n)
            if m is None:
                sys.exit(f"mangler {n} i {os.path.basename(tar_path)}")
            dest = os.path.join(mappe, os.path.basename(n))
            with t.extractfile(m) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            ut.append(dest)
    return ut


def kommando_hent(a):
    doc = json.load(open(KLIPP_JSON, encoding="utf-8"))
    cache = os.path.expanduser(a.cache)
    maal = finn_maal(a.maal)
    if not os.path.exists(maal):
        sys.exit("Finner ikke " + maal + "\nBygg først: cd src-tauri && cargo build --release --features maling --example maal")
    kilder = {k["id"]: k for k in doc["kilder"]}
    klipp = {k["id"]: k for k in doc["klipp"]}
    os.makedirs(LYD_DIR, exist_ok=True)
    skal = [k for k in doc["klipp"] if not a.bare or k["id"] in a.bare or k["id"] in
            {klipp[b].get("base") for b in a.bare if b in klipp}]
    if a.bare:  # babbel trengs av kafé-klippene
        if any(k.get("stoy") for k in skal):
            skal.append(klipp["stoy-babble"])
    stier = {}
    for k in skal:
        for kid in k.get("kilder", []):
            if kid not in stier:
                stier[kid] = hent_kilde(kilder[kid], cache)
    tmp = tempfile.mkdtemp(prefix="lla-testdata-", dir=cache)
    try:
        # 1) Rene klipp (og babbel, og filer)
        for k in skal:
            if k["type"] in ("forringet",):
                continue
            ut = os.path.join(LYD_DIR, k["id"] + (".mp3" if k["type"] == "fil" else ".wav"))
            if k["type"] == "fil":
                shutil.copyfile(stier[k["kilder"][0]], ut)
            elif k["type"] == "npsc":
                tarp = next(stier[x] for x in k["kilder"] if x.endswith("mp3"))
                mp = pakk_ut_tar(tarp, k["mp3"], tmp)
                dekod(maal, mp, k["gap_ms"], ut)
                for f in mp:
                    os.remove(f)
            elif k["type"] == "fleurs":
                tarp = next(stier[x] for x in k["kilder"] if x.endswith("tar"))
                mp = pakk_ut_tar(tarp, k["wav"], tmp)
                dekod(maal, mp, k["gap_ms"], ut)
                for f in mp:
                    os.remove(f)
            elif k["type"] == "stoykilde":
                tarp = next(stier[x] for x in k["kilder"] if x.endswith("mp3"))
                deler = []
                for d in k["deler"]:
                    mp = pakk_ut_tar(tarp, d["mp3"], tmp)
                    w = os.path.join(tmp, f"babbel-{d['speaker_id']}.wav")
                    dekod(maal, mp, 0, w)
                    deler.append(les_wav(w))
                    for f in mp:
                        os.remove(f)
                skriv_wav(ut, til_int16(stoy_babble(deler)))
            print("bygget", os.path.basename(ut), flush=True)
        # 2) Forringede
        for k in skal:
            if k["type"] != "forringet":
                continue
            base = les_wav(os.path.join(LYD_DIR, k["base"] + ".wav"))
            e = k["effekt"]
            if e == "telefon":
                y = effekt_telefon(base)
            elif e == "ekko":
                y = effekt_ekko(base)
            elif e == "bil":
                y = mix_snr(base, stoy_bil(len(base)), k["snr_db"])
            elif e == "kafe":
                y = mix_snr(base, list(les_wav(os.path.join(LYD_DIR, "stoy-babble.wav"))), k["snr_db"])
            else:
                sys.exit("ukjent effekt " + e)
            skriv_wav(os.path.join(LYD_DIR, k["id"] + ".wav"), y)
            print("bygget", k["id"] + ".wav", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if a.pin:
        for k in skal:
            fil = os.path.join(LYD_DIR, k["id"] + (".mp3" if k["type"] == "fil" else ".wav"))
            k["sha256"] = sha256_fil(fil)
            k["bytes"] = os.path.getsize(fil)
            if fil.endswith(".wav"):
                k["varighet_s"] = round((os.path.getsize(fil) - 44) / 32000, 1)
        json.dump(doc, open(KLIPP_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("SHA-256 og varighet skrevet til klipp.json")
    sys.exit(kommando_sjekk(a, doc))


def kommando_sjekk(a, doc=None):
    doc = doc or json.load(open(KLIPP_JSON, encoding="utf-8"))
    avvik = mangler = ok = 0
    for k in doc["klipp"]:
        fil = os.path.join(LYD_DIR, k["id"] + (".mp3" if k["type"] == "fil" else ".wav"))
        if not os.path.exists(fil):
            print("mangler", os.path.basename(fil))
            mangler += 1
        elif "sha256" not in k:
            print("ingen sum i klipp.json for", k["id"])
        elif sha256_fil(fil) != k["sha256"]:
            print("AVVIK  ", os.path.basename(fil))
            avvik += 1
        else:
            ok += 1
    print(f"{ok} stemmer, {avvik} avviker, {mangler} mangler")
    if mangler:
        return 1
    return 2 if avvik and a.streng else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kommando", choices=["hent", "sjekk", "velg"])
    ap.add_argument("--cache", default="~/lla-test/kilder")
    ap.add_argument("--maal", help="sti til maal-programmet (standard: src-tauri/target/release/examples/maal)")
    ap.add_argument("--bare", nargs="*", help="bare disse klipp-ID-ene (og det de trenger)")
    ap.add_argument("--pin", action="store_true", help="skriv SHA-256 og varighet for klippene til klipp.json")
    ap.add_argument("--streng", action="store_true", help="avvik i klippe-SHA gir exit 2")
    a = ap.parse_args()
    if a.kommando == "velg":
        kommando_velg(a)
    elif a.kommando == "hent":
        kommando_hent(a)
    else:
        sys.exit(kommando_sjekk(a))


if __name__ == "__main__":
    main()
