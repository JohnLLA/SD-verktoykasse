"""Ordfeilrate (WER), tegnfeilrate (CER) og normalisering for steg 3.

Bare standardbiblioteket. Denne normaliseringen gjelder bare målingen. Appens
tekst endres aldri (regel 4 i CLAUDE.md).

Normalisering (`normaliser`):
  1. Unicode NFC.
  2. Markører fra NPSC-fasiten fjernes: <ee>, <qq>, <mm>, <INAUDIBLE> og andre
     tegn i vinkelparenteser. `*` foran ukjente ord fjernes.
  3. Små bokstaver.
  4. Alt som ikke er bokstav eller siffer, blir mellomrom (tegnsetting,
     bindestrek, prosenttegn, apostrof). Bokstaver er alle Unicode-bokstaver,
     så æ, ø, å og aksentbokstaver beholdes.
  5. Mellomrom slås sammen.
Ikke gjort: tall til ord, forskjell på skrivemåter (sjøl/selv, nå/no),
sammensetninger. Slike avvik teller som feil.

`ord_streng` (for fasiter som har stor forbokstav og tegnsetting, f.eks. FLEURS):
  bare Unicode NFC og oppdeling på mellomrom. Store bokstaver og tegnsetting
  festet til ordene teller som feil.
"""
import re
import unicodedata

_MARKER = re.compile(r"<[^>]*>")


def normaliser(tekst):
    t = unicodedata.normalize("NFC", tekst)
    t = _MARKER.sub(" ", t)
    t = t.replace("*", "")
    t = t.lower()
    t = "".join(c if c.isalnum() else " " for c in t)
    return " ".join(t.split())


def ord_streng(tekst):
    return unicodedata.normalize("NFC", tekst).split()


def _align(ref, hyp):
    """Levenshtein-justering. Returnerer liste med (op, ref_idx, hyp_idx):
    op er 'C' (lik), 'S', 'D' (ref-ord mangler i hyp) eller 'I' (ekstra ord i hyp)."""
    n, m = len(ref), len(hyp)
    # Felles start og slutt trenger ingen DP.
    pre = 0
    while pre < n and pre < m and ref[pre] == hyp[pre]:
        pre += 1
    suf = 0
    while suf < n - pre and suf < m - pre and ref[n - 1 - suf] == hyp[m - 1 - suf]:
        suf += 1
    r = ref[pre : n - suf]
    h = hyp[pre : m - suf]
    rn, hm = len(r), len(h)
    ops = [("C", i, i) for i in range(pre)]
    if rn == 0 and hm == 0:
        pass
    elif rn == 0:
        ops += [("I", pre, pre + j) for j in range(hm)]
    elif hm == 0:
        ops += [("D", pre + i, pre) for i in range(rn)]
    else:
        # back[i][j]: 0 = diagonal, 1 = opp (D), 2 = venstre (I)
        back = [bytearray(hm + 1) for _ in range(rn + 1)]
        for j in range(1, hm + 1):
            back[0][j] = 2
        for i in range(1, rn + 1):
            back[i][0] = 1
        prev = list(range(hm + 1))
        for i in range(1, rn + 1):
            cur = [i] + [0] * hm
            ri = r[i - 1]
            bi = back[i]
            for j in range(1, hm + 1):
                d = prev[j - 1] + (0 if ri == h[j - 1] else 1)
                u = prev[j] + 1
                l = cur[j - 1] + 1
                if d <= u and d <= l:
                    cur[j] = d
                    bi[j] = 0
                elif u <= l:
                    cur[j] = u
                    bi[j] = 1
                else:
                    cur[j] = l
                    bi[j] = 2
            prev = cur
        i, j = rn, hm
        mid = []
        while i > 0 or j > 0:
            b = back[i][j]
            if b == 0:
                mid.append(("C" if r[i - 1] == h[j - 1] else "S", pre + i - 1, pre + j - 1))
                i -= 1
                j -= 1
            elif b == 1:
                mid.append(("D", pre + i - 1, pre + j))
                i -= 1
            else:
                mid.append(("I", pre + i, pre + j - 1))
                j -= 1
        mid.reverse()
        ops += mid
    for k in range(suf):
        ops.append(("C", n - suf + k, m - suf + k))
    return ops


def _runs(flags, minimum):
    """Lengder på sammenhengende True-løp som er minst `minimum` lange."""
    out, n = [], 0
    for f in flags + [False]:
        if f:
            n += 1
        else:
            if n >= minimum:
                out.append(n)
            n = 0
    return out


def vurder(ref_ord, hyp_ord, setninger=None, hopp_min=5):
    """Teller feil. `setninger`: liste med (start, slutt) som indekserer ref_ord
    (til å finne hoppede setninger). Returnerer dict.

    `hopp`: antall løp på minst `hopp_min` ref-ord på rad som mangler helt i
    utdata (innsatte ord midt i løpet bryter det ikke). `hoppede_setninger`:
    fasitsetninger på minst 4 ord der minst 80 % av ordene mangler."""
    ops = _align(ref_ord, hyp_ord)
    s = sum(1 for o in ops if o[0] == "S")
    d = sum(1 for o in ops if o[0] == "D")
    i = sum(1 for o in ops if o[0] == "I")
    n = len(ref_ord)
    del_flags = [o[0] == "D" for o in ops if o[0] != "I"]
    hopp = _runs(del_flags, hopp_min)
    # Lange innsettinger (gjentakelser/hallusinasjon): løp av I på minst 8 ord.
    ins_run = []
    cnt = 0
    for o in ops + [("X", 0, 0)]:
        if o[0] == "I":
            cnt += 1
        else:
            if cnt >= 8:
                ins_run.append(cnt)
            cnt = 0
    res = {
        "ref_ord": n,
        "hyp_ord": len(hyp_ord),
        "subst": s,
        "slettet": d,
        "innsatt": i,
        "wer": (s + d + i) / n if n else 0.0,
        "hopp": len(hopp),
        "hopp_ord": sum(hopp),
        "lange_innsettinger": len(ins_run),
        "lange_innsettinger_ord": sum(ins_run),
    }
    if setninger is not None:
        st = [o[0] for o in ops if o[0] != "I"]  # én per ref-ord
        hoppet = 0
        for a, b in setninger:
            ln = b - a
            if ln >= 4 and sum(1 for x in st[a:b] if x == "D") / ln >= 0.8:
                hoppet += 1
        res["hoppede_setninger"] = hoppet
        res["setninger"] = len(setninger)
    return res


def cer(ref_norm, hyp_norm):
    """Tegnfeilrate på normalisert tekst (mellomrom teller som tegn)."""
    r, h = ref_norm, hyp_norm
    if not r:
        return 0.0
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        ri = r[i - 1]
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j - 1] + (ri != h[j - 1]), prev[j] + 1, cur[j - 1] + 1)
        prev = cur
    return prev[-1] / len(r)
