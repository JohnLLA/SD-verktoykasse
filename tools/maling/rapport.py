#!/usr/bin/env python3
"""Lager tabeller (markdown) fra målingene til steg 3.

    python3 -I tools/maling/rapport.py tabeller --dato 2026-10-19      # skriver rapporter/kvalitet-<dato>.md
    python3 -I tools/maling/rapport.py feil --dato 2026-10-19 --kjoring <id> [<id> ...]
    python3 -I tools/maling/rapport.py hopp --dato 2026-10-19 --kjoring <id>

Leser rapporter/kvalitet-<dato>-tall.json og -tekst.json.gz (laget av maal.py analyser).
Bare standardbiblioteket.
"""
import argparse
import collections
import gzip
import json
import os
import sys

HER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HER)
import malform as mf  # noqa: E402
import maal  # noqa: E402
import ordfeil as of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HER))
SZ = ["small", "medium", "large"]
DEC = ["beam5", "greedy"]
REN_NB = ["nb-1", "nb-2", "nb-3", "nb-4"]
REN_NN = ["nn-1", "nn-2", "nn-3", "nn-4"]
DEGR = {"nb-1": ["nb-1", "nb-1-telefon", "nb-1-ekko", "nb-1-kafe", "nb-1-bil"],
        "nn-1": ["nn-1", "nn-1-telefon", "nn-1-kafe"]}
NAVN = {"verbatim": "lydrett (verbatim)", "semantic": "tolket, semantic (Beta)", "main": "tolket, hovedmodell",
        "semantic_ts": "semantic + tidsstempler", "main_ts": "hovedmodell + tidsstempler"}
MF = {"bokmal": "bokmål", "nynorsk": "nynorsk"}


def last(dato):
    base = os.path.join(ROOT, "rapporter", f"kvalitet-{dato}")
    rader = json.load(open(base + "-tall.json", encoding="utf-8"))
    with gzip.open(base + "-tekst.json.gz", "rt", encoding="utf-8") as f:
        tekster = json.load(f)
    return rader, tekster


def velg(rader, **kw):
    ut = []
    for r in rader:
        if r["cpu"] or r["grense_s"]:
            continue
        if all((v(r[k]) if callable(v) else (r[k] in v if isinstance(v, (list, set, tuple)) else r[k] == v))
               for k, v in kw.items()):
            ut.append(r)
    return ut


def feilrate(rader, nokkel, felt="wer"):
    """Samlet feilrate (feil / ord i fasit) over flere klipp."""
    feil = ord_ = 0
    for r in rader:
        m = r.get(nokkel)
        if not m:
            continue
        feil += m["subst"] + m["slettet"] + m["innsatt"]
        ord_ += m["ref_ord"]
    return None if ord_ == 0 else feil / ord_


def cer_snitt(rader, nokkel):
    v = [(r[nokkel]["cer"], r[nokkel]["ref_ord"]) for r in rader if r.get(nokkel) and "cer" in r[nokkel]]
    s = sum(w for _, w in v)
    return None if not s else sum(c * w for c, w in v) / s


def feilrate_uten_hopp(rader, nokkel):
    """Som feilrate, men ord i hopp (løp på minst 5 manglende fasitord) er trukket fra feilene."""
    feil = ord_ = 0
    for r in rader:
        m = r.get(nokkel)
        if not m:
            continue
        feil += m["subst"] + m["slettet"] + m["innsatt"] - m["hopp_ord"]
        ord_ += m["ref_ord"]
    return None if ord_ == 0 else feil / ord_


def pst(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f} %"


def tabell(kol, rader_):
    s = "| " + " | ".join(kol) + " |\n|" + "|".join("---" if i == 0 else "---:" for i in range(len(kol))) + "|\n"
    for r in rader_:
        s += "| " + " | ".join(str(c) for c in r) + " |\n"
    return s


def kolonner():
    return [(sz, d) for sz in SZ for d in DEC]


KOL_NAVN = [f"{sz} {d.replace('beam5', 'beam 5')}" for sz, d in kolonner()]


def wer_tabell(rader, malform, klipp, varianter, nokkel, tittel):
    ut = f"**{tittel}**\n\n"
    rs = []
    for v in varianter:
        rad = [NAVN[v]]
        for sz, d in kolonner():
            sel = velg(rader, malform=malform, klipp=klipp, variant=v, storrelse=sz, dekoding=d)
            rad.append(pst(feilrate(sel, nokkel)))
        rs.append(rad)
    return ut + tabell(["Modell"] + KOL_NAVN, rs) + "\n"


def lag_tabeller(rader, tekster, dato):
    o = [f"# Kvalitetsmåling {dato} (rådata-tabeller)\n",
         "Generert av `tools/maling/rapport.py` fra `rapporter/kvalitet-" + dato + "-tall.json`. "
         "Ordfeilrate (WER) er samlet over klippene (feil / ord i fasit), normalisert som beskrevet i "
         "`docs/kvalitet.md`. Metal på M5 Max.\n"]

    # 0 Sammendrag
    o.append("## 0. Sammendrag\n")
    def ant(ids, felt):
        return sum(len(of.normaliser(" ".join(maal.fasit_tekster(maal.les_fasit(k))[felt])).split()) for k in ids)
    o.append(f"Samlet feilrate over NPSC-klippene i egen målform (bokmål: nb-1..4, {ant(REN_NB, 'lydrett')} ord i fasit; "
             f"nynorsk: nn-1..4, {ant(REN_NN, 'lydrett')} ord) i hver celle. Tolket er målt mot den normaliserte fasiten, "
             "lydrett mot den ordrette. "
             "Én celle har bare 4 klipp: forskjeller på 3-4 prosentpoeng er innenfor støyen (se «Usikkerhet»).\n")
    for dec_navn, dec in (("Beam 5", ["beam5"]), ("Greedy", ["greedy"]), ("Beam 5 og greedy samlet", DEC)):
        rs = []
        for mfk, ren in (("bokmal", REN_NB), ("nynorsk", REN_NN)):
            for v, nok in (("verbatim", "mot_lydrett"), ("semantic", "mot_skriftlig"), ("main", "mot_skriftlig")):
                rad = [MF[mfk], NAVN[v]]
                for sz in SZ + [SZ]:
                    sel = velg(rader, malform=mfk, klipp=ren, variant=v, storrelse=sz, dekoding=dec)
                    rad.append(pst(feilrate(sel, nok)))
                rs.append(rad)
        o.append(f"**{dec_navn}**\n")
        o.append(tabell(["Målform", "Modell", "small", "medium", "large", "alle tre"], rs) + "\n")
    # Parvis sammenlikning semantic mot hovedmodell
    seg = main_ = lik = 0
    diffs = []
    for mfk, ren in (("bokmal", REN_NB), ("nynorsk", REN_NN)):
        for sz in SZ:
            for d in DEC:
                for kid in ren:
                    a = velg(rader, malform=mfk, klipp=kid, variant="semantic", storrelse=sz, dekoding=d)
                    b = velg(rader, malform=mfk, klipp=kid, variant="main", storrelse=sz, dekoding=d)
                    if a and b and a[0].get("mot_skriftlig") and b[0].get("mot_skriftlig"):
                        x, y = a[0]["mot_skriftlig"]["wer"], b[0]["mot_skriftlig"]["wer"]
                        diffs.append(x - y)
                        if abs(x - y) < 0.005:
                            lik += 1
                        elif x < y:
                            seg += 1
                        else:
                            main_ += 1
    if diffs:
        o.append(f"**Parvis: semantic mot hovedmodell** (samme klipp, størrelse og dekoding; {len(diffs)} par, "
                 f"forskjell under 0,5 prosentpoeng regnes som lik): hovedmodellen best i {main_}, semantic best i {seg}, "
                 f"lik i {lik}. Gjennomsnittlig forskjell (semantic minus hovedmodell): {100 * sum(diffs) / len(diffs):+.1f} prosentpoeng.\n")

    # 1 Hovedtabeller
    o.append("## 1. Ordfeilrate per målform, stil og størrelse\n")
    for mfk, ren in (("bokmal", REN_NB), ("nynorsk", REN_NN)):
        o.append(f"### {MF[mfk].capitalize()}: NPSC-klippene ({', '.join(ren)}), egen målform\n")
        o.append(wer_tabell(rader, mfk, ren, ["verbatim"], "mot_lydrett", "Lydrett mot ordrett fasit"))
        o.append(wer_tabell(rader, mfk, ren, ["semantic", "main"], "mot_skriftlig",
                            "Tolket mot normalisert fasit (tall med sifre)"))
        o.append(wer_tabell(rader, mfk, ren, ["semantic", "main"], "mot_lydrett",
                            "Tolket mot ordrett fasit (hvor mye som blir omskrevet eller fjernet)"))
        rs = []
        for v in ["verbatim", "semantic", "main"]:
            rad = [NAVN[v]]
            for sz, d in kolonner():
                rad.append(pst(feilrate_uten_hopp(velg(rader, malform=mfk, klipp=ren, variant=v, storrelse=sz,
                                                        dekoding=d), "mot_lydrett")))
            rs.append(rad)
        o.append("**Feilrate mot ordrett fasit når hoppede passasjer (≥5 ord på rad) er trukket fra**\n")
        o.append(tabell(["Modell"] + KOL_NAVN, rs) + "\n")
    o.append("### Bokmål: FLEURS (opplest, kvinner og menn)\n")
    o.append(wer_tabell(rader, "bokmal", ["fleurs-nb"], ["verbatim", "semantic", "main"], "mot_lydrett",
                        "Mot normalisert fasit (små bokstaver, uten tegnsetting)"))
    o.append(wer_tabell(rader, "bokmal", ["fleurs-nb"], ["semantic", "main"], "mot_skriftlig_streng",
                        "Tolket mot rå fasit, **streng** (store bokstaver og tegnsetting teller)"))
    o.append("### Tegnfeilrate (CER), samme klipp\n")
    rs = []
    for mfk, ren in (("bokmal", REN_NB), ("nynorsk", REN_NN)):
        for v, nok in (("verbatim", "mot_lydrett"), ("semantic", "mot_skriftlig"), ("main", "mot_skriftlig")):
            rad = [f"{MF[mfk]}, {NAVN[v]}"]
            for sz, d in kolonner():
                rad.append(pst(cer_snitt(velg(rader, malform=mfk, klipp=ren, variant=v, storrelse=sz, dekoding=d), nok)))
            rs.append(rad)
    o.append(tabell(["Rad"] + KOL_NAVN, rs) + "\n")

    # 2 Hopp
    o.append("## 2. Hoppet innhold\n")
    o.append("Samlet over NPSC-klippene (egen målform) og FLEURS (bokmål). «Hoppede setninger» = fasitsetninger "
             "på minst 4 ord der minst 80 % av ordene mangler i utdata. «Hopp» = løp på minst 5 fasitord på rad "
             "som mangler; «ord borte» er summen av ordene i slike løp, som andel av alle fasitord.\n")
    for dec in DEC:
        rs = []
        for mfk, ren in (("bokmal", REN_NB + ["fleurs-nb"]), ("nynorsk", REN_NN)):
            for v in ["verbatim", "semantic", "main"]:
                for sz in SZ:
                    sel = velg(rader, malform=mfk, klipp=ren, variant=v, storrelse=sz, dekoding=dec)
                    nok = "mot_lydrett"
                    ms = [r[nok] for r in sel if r.get(nok)]
                    if not ms:
                        continue
                    tot = sum(m["ref_ord"] for m in ms)
                    rs.append([MF[mfk], NAVN[v], sz, f"{sum(m['hoppede_setninger'] for m in ms)} av {sum(m['setninger'] for m in ms)}",
                               sum(m["hopp"] for m in ms), sum(m["hopp_ord"] for m in ms),
                               pst(sum(m["hopp_ord"] for m in ms) / tot), sum(m["lange_innsettinger"] for m in ms)])
        o.append(f"### {dec.replace('beam5', 'Beam 5')}\n")
        o.append(tabell(["Målform", "Modell", "Størrelse", "Hoppede setninger", "Hopp (≥5 ord)", "Ord i hopp",
                         "Ord borte", "Lange innsettinger (≥8 ord)"], rs) + "\n")
    o.append("### Samlet over alle størrelser og begge dekodinger (6 kjøringer per rad)\n")
    rs = []
    for mfk, ren in (("bokmal", REN_NB + ["fleurs-nb"]), ("nynorsk", REN_NN)):
        for v in ["verbatim", "semantic", "main"]:
            sel = velg(rader, malform=mfk, klipp=ren, variant=v)
            ms = [r["mot_lydrett"] for r in sel if r.get("mot_lydrett")]
            tot = sum(m["ref_ord"] for m in ms)
            rs.append([MF[mfk], NAVN[v], len(ms), f"{sum(m['hoppede_setninger'] for m in ms)} av {sum(m['setninger'] for m in ms)}",
                       sum(m["hopp"] for m in ms), pst(sum(m["hopp_ord"] for m in ms) / tot),
                       sum(m["lange_innsettinger"] for m in ms), pst(feilrate(sel, "mot_lydrett"))])
    o.append(tabell(["Målform", "Modell", "Kjøringer", "Hoppede setninger", "Hopp (≥5 ord)", "Ord borte", "Lange innsettinger",
                     "WER mot ordrett"], rs) + "\n")
    lang = velg(rader, klipp="lang-nb-30")
    if lang:
        rs = []
        for v in ["verbatim", "semantic", "main"]:
            for sz in SZ:
                for dec in DEC:
                    sel = [r for r in lang if r["variant"] == v and r["storrelse"] == sz and r["dekoding"] == dec]
                    if not sel or not sel[0].get("mot_lydrett"):
                        continue
                    m = sel[0]["mot_lydrett"]
                    rs.append([NAVN[v], sz, dec, pst(m["wer"]), pst(sel[0]["mot_skriftlig"]["wer"]),
                               f"{m['hoppede_setninger']} av {m['setninger']}", m["hopp"], pst(m["hopp_ord"] / m["ref_ord"]),
                               m["lange_innsettinger"]])
        o.append("### Lang fil (31 min, bokmål, mange talere, ikke delt opp av meg: appen deler selv i biter på 10 min)\n")
        o.append(tabell(["Modell", "Størrelse", "Dekoding", "WER mot ordrett", "WER mot normalisert", "Hoppede setn.",
                         "Hopp", "Ord borte", "Lange innsettinger"], rs) + "\n")

    # 3 Segmentering
    o.append("## 3. Segmentlengde (tidskoder)\n")
    o.append("Samlet over alle rene klipp og begge målformer, medium, beam 5. `_ts` = samme modell med verbatim-innstillingene "
             "fra `models.json` (`token_timestamps`, `max_len 60`, `split_on_word`).\n")
    rs = []
    for v in ["verbatim", "semantic", "main", "semantic_ts", "main_ts"]:
        sel = velg(rader, variant=v, storrelse="medium", dekoding="beam5", type=lambda t: t in ("npsc", "fleurs"),
                   klipp=lambda k: not k.startswith("lang"))
        sel = [r for r in sel if "seg_median_s" in r]
        if not sel:
            continue
        meds = sorted(r["seg_median_s"] for r in sel)
        rs.append([NAVN[v], len(sel), sum(r["segmenter"] for r in sel), f"{meds[len(meds) // 2]:.1f} s",
                   f"{max(r['seg_maks_s'] for r in sel):.0f} s",
                   pst(sum(r["seg_over_15s"] for r in sel) / sum(r["segmenter"] for r in sel)),
                   sum(r["seg_null"] for r in sel)])
    o.append(tabell(["Modell", "Kjøringer", "Segmenter", "Median lengde", "Lengste", "Andel over 15 s",
                     "Segmenter med null lengde"], rs) + "\n")
    # WER for _ts-variantene
    o.append("**Ordfeilrate med og uten tidsstempler (medium, beam 5)**\n")
    rs = []
    for mfk, ren in (("bokmal", REN_NB), ("nynorsk", REN_NN)):
        for v in ["semantic", "semantic_ts", "main", "main_ts"]:
            sel = velg(rader, malform=mfk, klipp=ren, variant=v, storrelse="medium", dekoding="beam5")
            if sel:
                rs.append([MF[mfk], NAVN[v], pst(feilrate(sel, "mot_skriftlig")), pst(feilrate(sel, "mot_lydrett"))])
    o.append(tabell(["Målform", "Modell", "WER mot normalisert", "WER mot ordrett"], rs) + "\n")

    # 4 Nynorsklekkasje
    o.append("## 4. Bokmålsformer i nynorsk utdata\n")
    o.append("Andel bokmålsmarkører av alle markører (liste i `tools/maling/malform.py`, ca. 70 entydige former). "
             "Lavere er bedre; 0 % betyr ingen kjente bokmålsformer. Et anslag nedenfra: bokmålsformer som ikke står på lista "
             "telles ikke. Markørtall i parentes er (bokmål/nynorsk) summert.\n")
    fa = {}
    for kid in REN_NB + REN_NN:
        f = maal.fasit_tekster(maal.les_fasit(kid))
        fa[kid] = f
    def fasit_andel(ids, felt):
        bm = nn = 0
        for k in ids:
            t = of.normaliser(" ".join(fa[k][felt]))
            a, b = mf.tell(t)
            bm += a
            nn += b
        return bm / (bm + nn) if bm + nn else None, bm + nn
    a1 = fasit_andel(REN_NN, "lydrett")
    a2 = fasit_andel(REN_NB, "maskinoversatt")
    a3 = fasit_andel(REN_NB, "lydrett")
    o.append(f"Kontroll av lista: nynorsk-fasit (NPSC nn) har {pst(a1[0])} bokmålsmarkører ({a1[1]} markører); "
             f"maskinoversatt nynorsk av bokmålstalene har {pst(a2[0])} ({a2[1]}); bokmål-fasit har {pst(a3[0])} ({a3[1]}).\n")
    for ren_navn, ren in (("Nynorsk tale (nn-1..4), `nn` som målform", REN_NN),
                          ("Bokmålstale (nb-1..4) som skal bli nynorsk, `nn` som målform", REN_NB)):
        rs = []
        for v in ["verbatim", "semantic", "main"]:
            rad = [NAVN[v]]
            for sz, d in kolonner():
                sel = velg(rader, malform="nynorsk", klipp=ren, variant=v, storrelse=sz, dekoding=d)
                bm = sum(r["markorer"][0] for r in sel)
                nn = sum(r["markorer"][1] for r in sel)
                rad.append(f"{pst(bm / (bm + nn)) if bm + nn else '–'} ({bm}/{nn})")
            rs.append(rad)
        o.append(f"**{ren_navn}**\n")
        o.append(tabell(["Modell"] + KOL_NAVN, rs) + "\n")
    o.append("**Nynorsk utdata fra bokmålstale: WER mot maskinoversatt (grov) fasit**\n")
    rs = []
    for v in ["verbatim", "semantic", "main"]:
        rad = [NAVN[v]]
        for sz, d in kolonner():
            sel = velg(rader, malform="nynorsk", klipp=REN_NB, variant=v, storrelse=sz, dekoding=d)
            rad.append(pst(feilrate(sel, "mot_maskinoversatt")))
        rs.append(rad)
    o.append(tabell(["Modell"] + KOL_NAVN, rs) + "\n")
    o.append("**Kontroll: bokmål som målform på nynorsk tale (andel bokmål bør være høy)**\n")
    rs = []
    for v in ["verbatim", "semantic", "main"]:
        rad = [NAVN[v]]
        for sz, d in kolonner():
            sel = velg(rader, malform="bokmal", klipp=REN_NN, variant=v, storrelse=sz, dekoding=d)
            bm = sum(r["markorer"][0] for r in sel)
            nn = sum(r["markorer"][1] for r in sel)
            rad.append(f"{pst(bm / (bm + nn)) if bm + nn else '–'} ({bm}/{nn})")
        rs.append(rad)
    o.append(tabell(["Modell"] + KOL_NAVN, rs) + "\n")

    # 5 Forringet lyd
    o.append("## 5. Dårlig lydkvalitet (simulert), beam 5\n")
    for base, ids in DEGR.items():
        mfk = "bokmal" if base.startswith("nb") else "nynorsk"
        rs = []
        for kid in ids:
            rad = [kid]
            for v, nok in (("verbatim", "mot_lydrett"), ("semantic", "mot_skriftlig"), ("main", "mot_skriftlig")):
                for sz in SZ:
                    sel = velg(rader, malform=mfk, klipp=kid, variant=v, storrelse=sz, dekoding="beam5")
                    rad.append(pst(feilrate(sel, nok)))
            rs.append(rad)
        kol = ["Klipp"] + [f"{'lydrett' if v == 'verbatim' else v} {sz}" for v in ("verbatim", "semantic", "main") for sz in SZ]
        o.append(f"**{base} ({MF[mfk]})**\n")
        o.append(tabell(kol, rs) + "\n")

    # 6 Fart
    o.append("## 6. Fart og minne (Metal, M5 Max)\n")
    o.append("Én prosess om gangen, ingen annen belastning bortsett fra at skrivebordet var i bruk (±20 % er realistisk). "
             "«Tid per 30 min» er regnet ut fra målt fart. «Oppstart» = en kjøring på 5 s lyd (laste modell, Metal). "
             "Toppminne er `ru_maxrss` for hele prosessen.\n")
    for kid, tittel in (("knuthamsun", "Naturlig lyd: Knut Hamsun, opplesning, 23 min (primær fartskilde)"),
                        ("lang-nb-30", "Stresstest: 31 min Stortingstaler limt sammen setning for setning (tett tale uten pauser, "
                                       "mange overganger)")):
        allr = [r for r in rader if r["klipp"] == kid and not r["cpu"] and not r["grense_s"]]
        over = {(r["variant"], r["storrelse"]): r["wall_s"] for r in rader if r["grense_s"] == 5 and not r["cpu"]
                and r["klipp"] == kid}
        rs = []
        for v in ["verbatim", "semantic", "main"]:
            for sz in SZ:
                for d in DEC:
                    sel = [r for r in allr if r["variant"] == v and r["storrelse"] == sz and r["dekoding"] == d]
                    if not sel:
                        continue
                    r = sel[0]
                    ov = over.get((v, sz))
                    rs.append([NAVN[v], sz, d, f"{r['wall_s']:.0f} s", f"{r['speed_x']:.1f}×",
                               f"{1800 / r['speed_x'] / 60:.1f} min", "–" if ov is None else f"{ov:.1f} s",
                               f"{r['peak_rss_mb']:.0f} MB"])
        o.append(f"**{tittel}**\n")
        o.append(tabell(["Modell", "Størrelse", "Dekoding", "Tid", "Fart", "Tid per 30 min", "Oppstart", "Toppminne"], rs) + "\n")
    for kid, tittel in (("knuthamsun", "Hamsun"), ("lang-nb-30", "stresstesten")):
        cpu = [r for r in rader if r["cpu"] and r["klipp"] == kid]
        if cpu:
            rs = [[NAVN[r["variant"]], r["storrelse"], r["dekoding"], r["threads"], f"{r['wall_s']:.0f} s",
                   f"{r['speed_x']:.1f}×", f"{r['peak_rss_mb']:.0f} MB"]
                  for r in sorted(cpu, key=lambda r: (r["variant"], SZ.index(r["storrelse"]), r["dekoding"]))]
            o.append(f"**Uten Metal (CPU-tråder på M5 Max), de første 10 minuttene av {tittel}.** Ikke representativt for en "
                     "Windows-PC (ARM-kjerner og Accelerate, ikke AVX2). Bare en grov indikasjon på hva «uten GPU» koster.\n")
            o.append(tabell(["Modell", "Størrelse", "Dekoding", "Tråder", "Tid", "Fart", "Toppminne"], rs) + "\n")

    # 7 per klipp
    o.append("## 7. WER per klipp (medium, beam 5)\n")
    rs = []
    for kid in REN_NB + REN_NN + ["fleurs-nb"]:
        mfk = "nynorsk" if kid.startswith("nn") else "bokmal"
        rad = [kid]
        for v, nok in (("verbatim", "mot_lydrett"), ("semantic", "mot_skriftlig"), ("main", "mot_skriftlig")):
            sel = velg(rader, malform=mfk, klipp=kid, variant=v, storrelse="medium", dekoding="beam5")
            rad.append(pst(feilrate(sel, nok)))
        rs.append(rad)
    o.append(tabell(["Klipp", "Lydrett", "Tolket semantic", "Tolket hovedmodell"], rs) + "\n")
    out = os.path.join(ROOT, "rapporter", f"kvalitet-{dato}.md")
    open(out, "w", encoding="utf-8").write("\n".join(o))
    print("skrev", out)


def refhyp(rid, rader, tekster, felt="mot_lydrett"):
    r = next(x for x in rader if x["id"] == rid)
    k = {c["id"]: c for c in maal.last_klipp()}[r["klipp"]]
    fa = maal.fasit_tekster(maal.les_fasit(k["fasit"]))
    nok = {"mot_lydrett": "lydrett", "mot_skriftlig": "skriftlig"}[felt]
    egen = (k["sprak"] == "nb") == (r["malform"] == "bokmal")
    if not egen:
        nok = "maskinoversatt"
    ref, gr = maal.ord_og_setninger(fa[nok])
    hyp = of.normaliser(" ".join(tekster[rid])).split()
    return ref, gr, hyp, of._align(ref, hyp), fa[nok]


def kommando_feil(a):
    rader, tekster = last(a.dato)
    sub = collections.Counter()
    dels = collections.Counter()
    ins = collections.Counter()
    for rid in a.kjoring:
        felt = "mot_lydrett" if "__verbatim__" in rid else "mot_skriftlig"
        ref, gr, hyp, ops, _ = refhyp(rid, rader, tekster, felt)
        for op, i, j in ops:
            if op == "S":
                sub[(ref[i], hyp[j])] += 1
            elif op == "D":
                dels[ref[i]] += 1
            elif op == "I":
                ins[hyp[j]] += 1
    print("Substitusjoner:", sub.most_common(a.n))
    print("Slettede ord:", dels.most_common(a.n))
    print("Innsatte ord:", ins.most_common(a.n))


def kommando_hopp(a):
    rader, tekster = last(a.dato)
    for rid in a.kjoring:
        felt = "mot_lydrett" if "__verbatim__" in rid else "mot_skriftlig"
        ref, gr, hyp, ops, setn = refhyp(rid, rader, tekster, felt)
        st = [o[0] for o in ops if o[0] != "I"]
        print("==", rid)
        for n, (s, e) in enumerate(gr):
            ln = e - s
            if ln >= 4 and sum(1 for x in st[s:e] if x == "D") / ln >= 0.5:
                print(f"  [{sum(1 for x in st[s:e] if x == 'D')}/{ln} ord borte] {setn[n]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kommando", choices=["tabeller", "feil", "hopp"])
    ap.add_argument("--dato", required=True)
    ap.add_argument("--kjoring", nargs="*", default=[])
    ap.add_argument("-n", type=int, default=25)
    a = ap.parse_args()
    if a.kommando == "tabeller":
        rader, tekster = last(a.dato)
        lag_tabeller(rader, tekster, a.dato)
    elif a.kommando == "feil":
        kommando_feil(a)
    else:
        kommando_hopp(a)


if __name__ == "__main__":
    main()
