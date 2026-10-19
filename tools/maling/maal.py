#!/usr/bin/env python3
"""Kjører målingen for steg 3 og regner ut ordfeilrate, fart og minne.

Utviklerverktøy (ikke en del av appen). Bare standardbiblioteket; kjør med -I.
Måler gjennom appens egen kjerne via `src-tauri/examples/maal.rs`:

    cd src-tauri && cargo build --release --features maling --example maal

    # 1) Kjør alle kombinasjoner (kan gjenopptas; ferdige kjøringer hoppes over):
    python3 -I tools/maling/maal.py kjor --modeller ~/lla-test/modeller --ut ~/lla-test/resultater

    # 2) Regn ut tall og lag tabeller:
    python3 -I tools/maling/maal.py analyser --ut ~/lla-test/resultater --dato 2026-10-19

Test-lyden må ligge i testdata/lyd/ (se tools/maling/hent_testdata.py).
Mål ikke mens noe annet tungt kjører på maskinen: fartstallene blir da feil.

Kombinasjoner: klipp x målform (bokmål/nynorsk) x variant (verbatim = lydrett,
semantic og main = to kandidater for tolket) x størrelse x dekoding (beam 5/greedy).
Langt klipp (30 min) kjøres bare med bokmål.
"""
import argparse
import gzip
import json
import os
import subprocess
import sys
import time

HER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HER)
import malform as mf  # noqa: E402
import ordfeil as of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HER))
TESTDATA = os.path.join(ROOT, "testdata")
LYD = os.path.join(TESTDATA, "lyd")
VARIANTER = ["verbatim", "semantic", "main"]
TS_VARIANTER = ["semantic_ts", "main_ts"]  # bare medium + beam 5
STORRELSER = ["small", "medium", "large"]
DEKODING = ["beam5", "greedy"]
MALFORMER = ["bokmal", "nynorsk"]


def modell_id(variant, storrelse, quant="q5_0"):
    # *_ts: samme modell som semantic/main, men med verbatim-innstillingene
    # (tidsstempler per token, maks 60 tegn per segment). Se docs/kvalitet.md.
    variant = variant.replace("_ts", "")
    return {"verbatim": f"nb-whisper-{storrelse}-verbatim-{quant}",
            "semantic": f"nb-whisper-{storrelse}-semantic-{quant}",
            "main": f"nb-whisper-{storrelse}-{quant}"}[variant]


def kjoring_id(klipp, malform, variant, storrelse, dekoding, cpu=False, grense=None):
    s = f"{klipp}__{malform}__{variant}__{storrelse}__{dekoding}"
    if cpu:
        s += "__cpu"
    if grense:
        s += f"__{grense}s"
    return s


def last_klipp():
    return json.load(open(os.path.join(TESTDATA, "klipp.json"), encoding="utf-8"))["klipp"]


def fil_for(k):
    return os.path.join(LYD, k["id"] + (".mp3" if k["type"] == "fil" else ".wav"))


def planlegg(a):
    """Liste med kjøringer: dict med klipp, malform, variant, storrelse, dekoding, cpu, grense."""
    klipp = [k for k in last_klipp() if k["type"] != "stoykilde"]
    if a.klipp:
        klipp = [k for k in klipp if k["id"] in a.klipp]
    planer = []
    for k in klipp:
        for sz in a.storrelser:
            for v in a.varianter:
                for d in a.dekoding:
                    for m in MALFORMER:
                        if k.get("lang") and m != "bokmal":
                            continue
                        if k["type"] == "forringet" and (d != "beam5" or (k["sprak"] == "nb") != (m == "bokmal")):
                            continue  # forringet lyd: bare egen målform og beam 5
                        if k.get("lang") and sz == "large" and d != "beam5":
                            continue  # 31 min med large tar 10-20 min per kjøring; beam 5 er nok
                        if k["id"] == "knuthamsun" and (not a.klipp or m != "bokmal"):
                            continue  # 23 min fart-fil (bare bokmål), tas bare med ved eksplisitt ønske
                        planer.append(dict(klipp=k["id"], malform=m, variant=v, storrelse=sz, dekoding=d,
                                           cpu=False, grense=a.grense))
    if "semantic" in a.varianter or "main" in a.varianter:
        for k in klipp:
            if k.get("lang") or k["id"] == "knuthamsun":
                continue
            for v in TS_VARIANTER:
                if v.replace("_ts", "") in a.varianter and "medium" in a.storrelser and "beam5" in a.dekoding:
                    for m in MALFORMER:
                        planer.append(dict(klipp=k["id"], malform=m, variant=v, storrelse="medium",
                                           dekoding="beam5", cpu=False, grense=a.grense))
    if a.cpu:
        # CPU uten Metal på de 10 første minuttene av et langt klipp (Windows-proxy, ikke representativt)
        lang_id = a.klipp[0] if a.klipp else "lang-nb-30"
        for sz in a.storrelser:
            for v in ("verbatim", "main"):
                for d in a.dekoding:
                    planer.append(dict(klipp=lang_id, malform="bokmal", variant=v, storrelse=sz,
                                       dekoding=d, cpu=True, grense=600))
    if (not a.klipp or a.klipp == ["knuthamsun"]) and not a.grense:
        # Fast oppstartskostnad (laste modell, Metal): 5 s av det lange klippet. Brukes til å skille
        # oppstart fra selve regnetiden.
        for sz in a.storrelser:
            for v in a.varianter:
                planer.append(dict(klipp=(a.klipp or ["lang-nb-30"])[0], malform="bokmal", variant=v, storrelse=sz,
                                   dekoding="beam5", cpu=False, grense=5))
    # Gruppér etter modell, så modellfilen ligger i filbufferet
    planer.sort(key=lambda p: (p["storrelse"], p["variant"], p["cpu"], p["klipp"], p["malform"], p["dekoding"]))
    return planer


def kommando_kjor(a):
    exe = a.maal or os.path.join(ROOT, "src-tauri", "target", "release", "examples",
                                 "maal.exe" if os.name == "nt" else "maal")
    if not os.path.exists(exe):
        sys.exit("Finner ikke " + exe + "\nBygg: cd src-tauri && cargo build --release --features maling --example maal")
    modeller = os.path.expanduser(a.modeller)
    ut = os.path.expanduser(a.ut)
    os.makedirs(ut, exist_ok=True)
    klipp = {k["id"]: k for k in last_klipp()}
    planer = planlegg(a)
    er_fart = lambda p: p["klipp"].startswith("lang") or p["klipp"] == "knuthamsun" or p["cpu"] or p["grense"]  # noqa: E731
    if a.uten_fart:
        planer = [p for p in planer if not er_fart(p)]
    if a.bare_fart:
        planer = [p for p in planer if er_fart(p)]
    if a.omvendt:
        planer.reverse()
    if a.del_:
        k, n = (int(x) for x in a.del_.split("/"))
        planer = [p for i, p in enumerate(planer) if i % n == k]
    print(f"{len(planer)} kjøringer", flush=True)
    feil = 0
    t0 = time.time()
    for n, p in enumerate(planer, 1):
        rid = kjoring_id(p["klipp"], p["malform"], p["variant"], p["storrelse"], p["dekoding"], p["cpu"], p["grense"])
        fut = os.path.join(ut, rid + ".json")
        if os.path.exists(fut):
            continue
        mid = modell_id(p["variant"], p["storrelse"])
        if not os.path.exists(os.path.join(modeller, mid + ".bin")):
            print("hopper over (mangler modell)", mid)
            continue
        cmd = [exe, "run", "--model-dir", modeller, "--model-id", mid, "--audio", fil_for(klipp[p["klipp"]]),
               "--malform", p["malform"], "--decoding", p["dekoding"], "--out", fut + ".tmp"]
        if p["variant"].endswith("_ts"):
            cmd += ["--options", "verbatim"]
        if p["cpu"]:
            cmd.append("--no-gpu")
        if p["grense"]:
            cmd += ["--limit-secs", str(p["grense"])]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            feil += 1
            print(f"[{n}/{len(planer)}] FEIL {rid}: {r.stderr.strip()[-200:]}")
            continue
        os.replace(fut + ".tmp", fut)
        print(f"[{n}/{len(planer)}] {rid}: {r.stdout.strip()}  ({(time.time() - t0) / 60:.1f} min)", flush=True)
    sys.exit(1 if feil else 0)


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------
def les_fasit(fid):
    return json.load(open(os.path.join(TESTDATA, "fasit", fid + ".json"), encoding="utf-8"))


def fasit_tekster(f):
    """Returnerer dict: nøkkel -> liste med setninger (tekst)."""
    s = f["setninger"]
    d = {"lydrett": [x["lydrett"] for x in s], "skriftlig": [x["skriftlig"] for x in s]}
    if "maskinoversatt" in s[0]:
        d["maskinoversatt"] = [x["maskinoversatt"] for x in s]
    return d


def ord_og_setninger(setninger, streng=False):
    """Ordliste for hele fasiten og (start, slutt) per setning."""
    ord_, grenser = [], []
    for t in setninger:
        w = of.ord_streng(t) if streng else of.normaliser(t).split()
        grenser.append((len(ord_), len(ord_) + len(w)))
        ord_ += w
    return ord_, grenser


def mål(hyp_tekst, setninger, streng=False, med_cer=True):
    ref, gr = ord_og_setninger(setninger, streng)
    hyp = of.ord_streng(hyp_tekst) if streng else of.normaliser(hyp_tekst).split()
    res = of.vurder(ref, hyp, gr)
    if med_cer and not streng:
        res["cer"] = cer_bandet(" ".join(ref), " ".join(hyp))
    return res


def cer_bandet(r, h):
    """Tegnfeilrate med bånd (Ukkonen) for fart. Eksakt så lenge distansen er mindre enn båndet."""
    if not r:
        return 0.0
    n, m = len(r), len(h)
    band = max(64, abs(n - m) + 64)
    while True:
        INF = 10 ** 9
        prev = {j: j for j in range(0, min(m, band) + 1)}
        for i in range(1, n + 1):
            lo, hi = max(0, i - band), min(m, i + band)
            cur = {}
            for j in range(lo, hi + 1):
                if j == 0:
                    cur[j] = i
                    continue
                best = min(prev.get(j - 1, INF) + (r[i - 1] != h[j - 1]), prev.get(j, INF) + 1, cur.get(j - 1, INF) + 1)
                cur[j] = best
            prev = cur
        d = prev.get(m, INF)
        if d <= band:
            return d / n
        band *= 4


def kommando_analyser(a):
    ut = os.path.expanduser(a.ut)
    klipp = {k["id"]: k for k in last_klipp()}
    fasiter = {}
    rader = []
    tekster = {}
    filer = sorted(f for f in os.listdir(ut) if f.endswith(".json"))
    for fn in filer:
        rid = fn[:-5]
        doc = json.load(open(os.path.join(ut, fn), encoding="utf-8"))
        deler = rid.split("__")
        kid, malform, variant, sz, dec = deler[:5]
        extra = deler[5:]
        k = klipp[kid]
        tekst = " ".join(s["text"] for s in doc["segments"])
        tekster[rid] = [s["text"] for s in doc["segments"]]
        r = {"id": rid, "klipp": kid, "type": k["type"], "malform": malform, "variant": variant, "storrelse": sz,
             "dekoding": dec, "cpu": "cpu" in extra, "grense_s": next((int(e[:-1]) for e in extra if e.endswith("s")), None),
             "duration_s": doc["duration_s"], "wall_s": doc["wall_s"], "speed_x": doc["speed_x"],
             "peak_rss_mb": doc["peak_rss_mb"], "threads": doc["threads"], "gpu": doc["gpu"],
             "segmenter": len(doc["segments"]), "ord": len(of.normaliser(tekst).split()), "chunks": doc["chunks"]}
        lengder = sorted((x["end_ms"] - x["start_ms"]) / 1000 for x in doc["segments"])
        if lengder:
            r["seg_median_s"] = lengder[len(lengder) // 2]
            r["seg_maks_s"] = lengder[-1]
            r["seg_over_15s"] = sum(1 for x in lengder if x > 15)
            r["seg_null"] = sum(1 for x in lengder if x < 0.05)
        norm = of.normaliser(tekst)
        r["bokmalsandel"] = mf.bokmalsandel(norm)
        r["markorer"] = list(mf.tell(norm))
        if k.get("ingen_fasit") or r["grense_s"]:
            rader.append(r)
            continue
        fid = k["fasit"]
        if fid not in fasiter:
            fasiter[fid] = fasit_tekster(les_fasit(fid))
        fa = fasiter[fid]
        egen = (k["sprak"] == "nb") == (malform == "bokmal")
        langt = bool(k.get("lang"))
        if egen:
            r["mot_lydrett"] = mål(tekst, fa["lydrett"], med_cer=not langt)
            r["mot_skriftlig"] = mål(tekst, fa["skriftlig"], med_cer=not langt)
            if k["type"] == "fleurs":
                r["mot_skriftlig_streng"] = mål(tekst, fa["skriftlig"], streng=True)
        elif "maskinoversatt" in fa:
            # nynorsk utdata fra bokmålstale (eller omvendt): bare maskinoversatt fasit finnes
            r["mot_maskinoversatt"] = mål(tekst, fa["maskinoversatt"], med_cer=False)
        rader.append(r)
    dato = a.dato or time.strftime("%Y-%m-%d")
    base = os.path.join(ROOT, "rapporter", f"kvalitet-{dato}")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    json.dump(rader, open(base + "-tall.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    with gzip.open(base + "-tekst.json.gz", "wt", encoding="utf-8") as f:
        json.dump(tekster, f, ensure_ascii=False)
    print(f"{len(rader)} kjøringer analysert -> {base}-tall.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kommando", choices=["kjor", "analyser"])
    ap.add_argument("--modeller", default="~/lla-test/modeller")
    ap.add_argument("--ut", default="~/lla-test/resultater")
    ap.add_argument("--maal")
    ap.add_argument("--klipp", nargs="*")
    ap.add_argument("--storrelser", nargs="+", default=STORRELSER)
    ap.add_argument("--varianter", nargs="+", default=VARIANTER)
    ap.add_argument("--dekoding", nargs="+", default=DEKODING)
    ap.add_argument("--cpu", action="store_true", help="ta med CPU-kjøringer uten Metal (10 min av det lange klippet)")
    ap.add_argument("--grense", type=int, help="bare de første N sekundene av hvert klipp (bare fart, ingen WER)")
    ap.add_argument("--uten-fart", action="store_true",
                    help="hopp over de lange klippene, CPU- og oppstartskjøringene (de skal kjøres alene)")
    ap.add_argument("--bare-fart", action="store_true", help="bare de lange klippene, CPU- og oppstartskjøringene")
    ap.add_argument("--del", dest="del_", help="K/N: ta hver N-te kjøring, fra nr. K (for parallelle prosesser)")
    ap.add_argument("--omvendt", action="store_true", help="kjør planen bakfra (ekstra prosess som møter de andre midt i)")
    ap.add_argument("--dato")
    a = ap.parse_args()
    {"kjor": kommando_kjor, "analyser": kommando_analyser}[a.kommando](a)


if __name__ == "__main__":
    main()
