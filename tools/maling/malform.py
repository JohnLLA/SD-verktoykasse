"""Anslag for hvor mye bokmål som er igjen i nynorsk utdata (og omvendt).

Ordlista er håndskrevet og liten: bare former som er entydig bokmål eller
entydig nynorsk (ikke sideformer som begge målformer tillater, f.eks. «nå»/«no»
og «også»/«òg», og ikke ord som er like). Tallet er derfor et anslag nedenfra:
det finner ikke bokmålsformer som ikke står på lista (bestemt flertall på -ene,
infinitiv på -e i a-verb og mange andre).

`bokmalsandel` = bokmålsmarkører / (bokmålsmarkører + nynorskmarkører), regnet
på normalisert tekst. None hvis teksten ikke har noen markører.
"""

# bokmål -> nynorsk (flere nynorske former skilles med |)
PAR = {
    "ikke": "ikkje", "hva": "kva", "hvem": "kven", "hvor": "kor|kvar",
    "hvorfor": "kvifor", "hvilken": "kva", "jeg": "eg", "fra": "frå",
    "noe": "noko", "noen": "nokon|nokre", "bare": "berre", "mye": "mykje",
    "hjem": "heim", "hjemme": "heime", "hjemmet": "heimen", "hvis": "viss",
    "selv": "sjølv|sjøl", "sammen": "saman", "siden": "sidan",
    "ble": "vart|blei", "vært": "vore", "være": "vere", "gjøre": "gjere",
    "gjør": "gjer", "sier": "seier", "kommer": "kjem", "mer": "meir",
    "flere": "fleire", "uten": "utan", "hos": "hjå", "hver": "kvar",
    "hvert": "kvart", "helt": "heilt", "ellers": "elles", "sted": "stad",
    "steder": "stader", "mennesker": "menneske", "eneste": "einaste",
    "dem": "dei", "hun": "ho", "disse": "desse", "tidligere": "tidlegare",
    "videre": "vidare", "løsning": "løysing", "løsninger": "løysingar",
    "uke": "veke", "uker": "veker", "ganger": "gonger", "synes": "synest",
    "mener": "meiner", "trenger": "treng", "bruker": "brukar",
    "nordlendinger": "nordlendingar", "sørlendinger": "sørlendingar",
    "trøndere": "trøndarar", "innvandrere": "innvandrarar",
    "politikere": "politikarar", "lærere": "lærarar", "arbeidere": "arbeidarar",
    "innbyggere": "innbyggjarar", "kommunene": "kommunane", "gutter": "gutar",
    "regioner": "regionar", "bedre": "betre", "annet": "anna", "norge": "noreg",
}

BOKMAL = frozenset(PAR)
NYNORSK = frozenset(f for v in PAR.values() for f in v.split("|")) - BOKMAL


def tell(norm_tekst):
    bm = nn = 0
    for w in norm_tekst.split():
        if w in BOKMAL:
            bm += 1
        elif w in NYNORSK:
            nn += 1
    return bm, nn


def bokmalsandel(norm_tekst):
    bm, nn = tell(norm_tekst)
    return None if bm + nn == 0 else bm / (bm + nn)
