"""redact: find personal data in a PDF and redact it for real.

Two steps:
  find_to_plan()      -> writes a JSON plan the user can edit (strike hits)
  redact_with_plan()  -> applies the plan with PyMuPDF redactions and only
                         writes the result if an independent check finds
                         none of the redacted values left in the file.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

from jv_common import UserError, safe_output_path, sha256_file

from . import __version__
from .detect import (
    TYPE_LABELS,
    Hit,
    collapse_ws,
    find_hits,
    find_in_string,
    find_rejected,
    normalize_text,
)
from .prepare import (
    Working,
    link_strings,
    page_label_strings,
    restore_boxes,
    working_copy,
)
from .verify import Kept, RejectedLeft, Value, content_object_values, extract_all, norm_text, verify

PLAN_VERSION = 1
PLAN_TOOL = "redact"
RECT_TOLERANCE = 0.5

Progress = Callable[[float], None] | None

# What apply_redactions removes under each rectangle.
REDACT_OPTIONS = {
    "text": pymupdf.PDF_REDACT_TEXT_REMOVE,  # also invisible (OCR) text
    "images": pymupdf.PDF_REDACT_IMAGE_PIXELS,  # blank the pixels under the box
    "graphics": pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
}

PLAN_HELP = (
    "Gå gjennom treffene. Stryk et treff ved å sette \"sladd\" til false. Ikke "
    "slett treff og ikke endre andre felt eller listen «termer»: planen er knyttet "
    "til PDF-en med SHA-256, og sladd nekter å bruke en plan som ikke stemmer med "
    "det verktøyet finner i PDF-en. Nye termer legges i termfilen, og planen lages "
    "på nytt med «jv redact finn». "
    "«plassering» sier hvor treffet er: «side» (synlig tekst), «utenfor sideflaten», "
    "«skjult lag» (innholdslag som er slått av), eller «bokmerke», «lenke», "
    "«sidelabel» og «metadata». Bokmerker, lenker til adresser, sidelabels og "
    "metadata fjernes alltid, også om treffet strykes. Oppføringer med "
    "\"forkastet\": true er mulige numre der sifrene står langt fra hverandre "
    "(trolig tabellceller); de er ikke merket for sladding, men kan sladdes ved å "
    "sette \"sladd\" til true. Tallrekker som inneholder en dato med "
    "firesifret år, et saksnummer som 2026/2911 eller et beløp med desimalkomma og to "
    "desimaler (nabokolonner i en tabell) er utelatt fra planen og blir ikke "
    "sladdet. Les gjennom dokumentet selv."
)

# placements of hits in the page content (have rectangles) and elsewhere
PAGE_PLACEMENTS = ("side", "utenfor sideflaten", "skjult lag")
OTHER_PLACEMENTS = ("bokmerke", "lenke", "sidelabel", "metadata")


# --------------------------------------------------------------------- input


def _open_pdf(path: Path) -> pymupdf.Document:
    if not path.exists():
        raise UserError(f"Finner ikke filen «{path}».")
    if not path.is_file():
        raise UserError(f"«{path}» er ikke en fil.")
    if path.stat().st_size == 0:
        raise UserError(f"Filen «{path.name}» er tom.")
    with open(path, "rb") as fh:
        head = fh.read(1024)
    if b"%PDF-" not in head:
        raise UserError(f"«{path.name}» er ikke en PDF-fil.")
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - any parse error is a user error
        raise UserError(
            f"Klarte ikke å åpne «{path.name}» som PDF. Filen er trolig ødelagt eller ufullstendig."
        ) from exc
    if not doc.is_pdf:
        doc.close()
        raise UserError(f"«{path.name}» er ikke en PDF-fil.")
    if doc.needs_pass:
        doc.close()
        raise UserError(
            f"«{path.name}» er passordbeskyttet. Fjern passordet først og prøv igjen."
        )
    if doc.page_count == 0:
        doc.close()
        raise UserError(f"«{path.name}» har ingen sider.")
    return doc


def _check_text_layer(work: Working, name: str) -> list[str]:
    """Raise if there is no text at all; warn about pages without text."""
    warnings: list[str] = []
    text_pages = 0
    for page in work.doc:
        if page.get_text("text", clip=pymupdf.INFINITE_RECT()).strip():
            text_pages += 1
        elif page.get_images():
            warnings.append(
                f"Side {page.number + 1} har ikke tekstlag (ser skannet ut) og er "
                "ikke kontrollert. Kjør «jv ocr» først hvis siden har tekst."
            )
    if text_pages == 0:
        raise UserError(
            f"«{name}» har ikke tekstlag og ser ut som en skannet PDF. "
            "Kjør «jv ocr» på filen først, og kjør så redact på resultatet."
        )
    if work.had_layers:
        warnings.append(
            "PDF-en har innholdslag (OCG). Alle lag er tatt med i søket, og i den "
            "sladdede filen er lagene slått sammen, så innhold som var skjult, blir synlig."
        )
    return warnings


def _open_working(path: Path) -> Working:
    _open_pdf(path).close()  # Norwegian errors for bad input
    return working_copy(path.read_bytes(), flatten_layers=True)


def _other_hits(work: Working, terms: list[str]) -> list[Hit]:
    """Hits outside the page content: outline, links, page labels, metadata."""
    doc = work.doc
    sources: list[tuple[str, int | None, str]] = []
    for level, title, page, *_ in doc.get_toc(simple=False):
        sources.append(("bokmerke", page if page and page > 0 else None, str(title)))
    for page, uri in link_strings(doc):
        sources.append(("lenke", page, uri))
    for page, prefix in page_label_strings(doc):
        sources.append(("sidelabel", page, prefix))
    for key, value in (doc.metadata or {}).items():
        if key not in ("format", "encryption") and value:
            sources.append(("metadata", None, str(value)))
    xmp = doc.get_xml_metadata() or ""
    if xmp:
        sources.append(("metadata", None, xmp))
    hits: list[Hit] = []
    seen: set[tuple] = set()
    for placement, page, text in sources:
        for typ, found, normalized, excerpt in find_in_string(text, terms):
            key = (typ, found, placement, page)
            if key in seen:
                continue
            seen.add(key)
            hits.append(Hit(typ, found, normalized, page, excerpt, [], placement))
    return hits


NOTHING_MARKED = "Ingen treff ble merket for sladding. Les gjennom dokumentet selv."
NO_HITS = "Fant ingen treff. Det betyr ikke at dokumentet er fritt for personopplysninger. Les gjennom dokumentet selv."

REJECT_SUMMARY = (
    "{n} mulige fødselsnumre/telefonnumre ble IKKE merket for sladding (stor "
    "avstand mellom sifrene) – gå gjennom planen."
)
REJECT_LEFT = (
    "{n} mulige fødselsnumre/telefonnumre ble IKKE sladdet (stor avstand mellom "
    "sifrene, \"forkastet\": true og \"sladd\": false i planen) og står igjen i "
    "dokumentet. Sett \"sladd\" til true i planen hvis de skal bort."
)


def _page_hits(work: Working, terms: list[str], progress: Progress = None) -> list[Hit]:
    """Page hits followed by the rejected number candidates (flagged)."""
    hits = find_hits(work.doc, terms, progress) + find_rejected(work.doc, terms)
    for h in hits:
        visible = work.visible[h.page - 1]
        h.offset = (visible.x0, visible.y0)
        if not any(pymupdf.Rect(r).intersects(visible) for r in h.rects):
            h.placement = "utenfor sideflaten"
    return hits


PROMOTED = (
    "{n} treff med stor avstand mellom sifrene er merket for sladding likevel, fordi "
    "samme verdi står som ett tekststykke i dokumentet (synlig med justering, eller "
    "skjult). Finnes en skjult kopi, stopper «sladd» uten å lage fil."
)
HIDDEN_TEXT = (
    "{n} mulige personopplysninger finnes i innholdsstrømmene som ett tekststykke, "
    "men kan ikke plasseres som lesbar tekst på siden (skjult eller usynlig tekst, "
    "f.eks. med horisontal skalering 0). Slik tekst kan ikke sladdes, og «sladd» vil "
    "stoppe uten å lage fil."
)


def _collect_hits(input_path: Path, work: Working, terms: list[str], progress: Progress = None) -> tuple[list[Hit], list[str]]:
    """All hits as finn and sladd see them (the same in both), plus warnings.

    A rejected candidate (digit groups far apart on the page) becomes a
    normal hit when the same value also stands as one text object somewhere
    in a content stream: then it is not just two table cells.
    """
    warnings: list[str] = []
    hits = _page_hits(work, terms, progress)
    if work.had_layers:
        _mark_hidden_layer_hits(input_path, hits, terms)
    in_objects = content_object_values(work.doc, terms)
    on_page = {(h.type, h.normalized) for h in hits}
    promoted = 0
    for h in hits:
        if h.rejected and (h.type, h.normalized) in in_objects:
            h.rejected = False
            h.quiet = False
            h.reason = ""
            promoted += 1
    if promoted:
        warnings.append(PROMOTED.format(n=promoted))
    hidden = {v for v in in_objects if v[0] != "term" and v not in on_page}
    if hidden:
        warnings.append(HIDDEN_TEXT.format(n=len(hidden)))
    hits += _other_hits(work, terms)
    return hits, warnings


def _mark_hidden_layer_hits(path: Path, hits: list[Hit], terms: list[str]) -> None:
    """Hits that only show up when the layers are flattened."""
    shown = working_copy(path.read_bytes(), flatten_layers=False)
    try:
        visible = {
            (h.type, h.text, h.page, tuple(map(tuple, h.rects)))
            for h in find_hits(shown.doc, terms) + find_rejected(shown.doc, terms)
        }
    finally:
        shown.doc.close()
    for h in hits:
        if h.placement == "side" and (h.type, h.text, h.page, tuple(map(tuple, h.rects))) not in visible:
            h.placement = "skjult lag"


def read_terms(path: Path | None) -> list[str]:
    if path is None:
        return []
    if not path.is_file():
        raise UserError(f"Finner ikke termfilen «{path}».")
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UserError(f"Termfilen «{path.name}» er ikke UTF-8-tekst.") from exc
    terms: list[str] = []
    for line in raw.splitlines():
        term = collapse_ws(normalize_text(line))
        if term and term not in terms:
            terms.append(term)
    return terms


# ---------------------------------------------------------------------- find


@dataclass
class FindResult:
    plan_path: Path
    hits: list[Hit]
    warnings: list[str] = field(default_factory=list)


def _hit_to_json(i: int, hit: Hit) -> dict[str, Any]:
    return {
        "id": f"t{i}",
        "type": hit.type,
        "tekst": hit.text,
        "normalisert": hit.normalized,
        "side": hit.page,
        "utdrag": hit.excerpt,
        "plassering": hit.placement,
        "rektangler": hit.plan_rects(),
        "sladd": not hit.rejected,
        **({"forkastet": True, "grunn": hit.reason} if hit.rejected else {}),
    }


def find_to_plan(
    input_path: Path,
    out_dir: Path,
    terms_path: Path | None = None,
    progress: Progress = None,
) -> FindResult:
    terms = read_terms(terms_path)
    work = _open_working(input_path)
    try:
        warnings = _check_text_layer(work, input_path.name)
        hits, extra = _collect_hits(input_path, work, terms, progress)
        warnings += extra
    finally:
        work.doc.close()
    n_quiet = sum(1 for h in hits if h.quiet)
    hits = [h for h in hits if not h.quiet]
    rejected = [h for h in hits if h.rejected]
    if rejected:
        warnings.append(REJECT_SUMMARY.format(n=len(rejected)))
    if n_quiet:
        warnings.append(
            f"{n_quiet} tallrekker er ikke tatt med i planen fordi de har punktum, skråstrek "
            "eller komma mellom sifrene og ser ut som datoer, beløp eller saksnumre fra "
            "nabokolonner i en tabell (de kan i teorien være et fødselsnummer skrevet "
            "uvanlig). Les gjennom dokumentet selv."
        )
    outside = [h for h in hits if h.placement != "side"]
    if outside:
        warnings.append(
            f"{len(outside)} treff ligger ikke som synlig tekst på siden "
            "(se «plassering» i planen)."
        )
    plan = {
        "verktoy": PLAN_TOOL,
        "versjon": __version__,
        "plan_versjon": PLAN_VERSION,
        "kilde": {
            "fil": input_path.name,
            "sha256": sha256_file(input_path),
            "termer_sha256": terms_digest(terms),
        },
        "termer": terms,
        "veiledning": PLAN_HELP,
        "treff": [_hit_to_json(i + 1, h) for i, h in enumerate(hits)],
    }
    plan_path = safe_output_path(input_path, out_dir, "-treff.json")
    with open(plan_path, "x", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return FindResult(plan_path, hits, warnings)


def terms_digest(terms: list[str]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(terms, ensure_ascii=False).encode("utf-8")).hexdigest()


def count_by_type(items) -> str:
    counts: dict[str, int] = {}
    for it in items:
        t = it.type if isinstance(it, Hit) else it["type"]
        counts[t] = counts.get(t, 0) + 1
    if not counts:
        return "ingen treff"
    order = list(TYPE_LABELS)
    keys = sorted(counts, key=lambda t: order.index(t) if t in order else len(order))
    parts = [f"{counts[t]} {TYPE_LABELS.get(t, t)}" for t in keys]
    return ", ".join(parts)


# ---------------------------------------------------------------------- plan

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_BAD_PLAN = "Planen «{name}» er ugyldig eller endret: {why}. Lag en ny med «jv redact finn»."


def load_plan(plan_path: Path) -> dict[str, Any]:
    name = plan_path.name
    if not plan_path.is_file():
        raise UserError(f"Finner ikke planfilen «{plan_path}».")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise UserError(f"Planfilen «{name}» er ikke UTF-8-tekst.") from exc
    except json.JSONDecodeError as exc:
        raise UserError(
            f"Planfilen «{name}» er ikke gyldig JSON (feil på linje {exc.lineno}, "
            f"tegn {exc.colno})."
        ) from exc

    def bad(why: str) -> UserError:
        return UserError(_BAD_PLAN.format(name=name, why=why))

    if not isinstance(plan, dict):
        raise bad("toppnivået er ikke et objekt")
    if plan.get("verktoy") != PLAN_TOOL or plan.get("plan_versjon") != PLAN_VERSION:
        raise bad("den er ikke laget av «jv redact finn» (feil verktøy eller versjon)")
    kilde = plan.get("kilde")
    if not isinstance(kilde, dict) or not isinstance(kilde.get("sha256"), str):
        raise bad("mangler kilde.sha256")
    if not _SHA_RE.match(kilde["sha256"]):
        raise bad("kilde.sha256 er ikke en SHA-256-verdi")
    terms = plan.get("termer")
    if not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
        raise bad("«termer» må være en liste med tekst")
    if kilde.get("termer_sha256") != terms_digest(terms):
        raise bad(
            "listen «termer» er endret. Nye termer må legges i termfilen, og "
            "planen lages på nytt med «jv redact finn --terms»"
        )
    items = plan.get("treff")
    if not isinstance(items, list):
        raise bad("«treff» må være en liste")
    ids: set[str] = set()
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise bad(f"treff nr. {n} er ikke et objekt")
        for key, typ in (
            ("id", str), ("type", str), ("tekst", str), ("rektangler", list), ("plassering", str)
        ):
            if not isinstance(item.get(key), typ):
                raise bad(f"treff nr. {n} mangler eller har feil «{key}»")
        placement = item["plassering"]
        if placement not in PAGE_PLACEMENTS + OTHER_PLACEMENTS:
            raise bad(f"treff nr. {n} har ukjent plassering «{placement}»")
        side = item.get("side")
        side_ok = isinstance(side, int) and not isinstance(side, bool) and side >= 1
        if not side_ok and not (side is None and placement in OTHER_PLACEMENTS):
            raise bad(f"treff nr. {n} har ugyldig «side»")
        if not isinstance(item.get("sladd"), bool):
            raise bad(f"treff nr. {n}: «sladd» må være true eller false")
        if not isinstance(item.get("forkastet", False), bool):
            raise bad(f"treff nr. {n}: «forkastet» må være true eller false")
        if item["type"] not in TYPE_LABELS:
            raise bad(f"treff nr. {n} har ukjent type «{item['type']}»")
        rects = item["rektangler"]
        if placement in OTHER_PLACEMENTS:
            if rects:
                raise bad(f"treff nr. {n} har «rektangler», men ligger ikke på en side")
        elif not rects or not all(
            isinstance(r, list)
            and len(r) == 4
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r)
            for r in rects
        ):
            raise bad(f"treff nr. {n} har ugyldige «rektangler»")
        if item["id"] in ids:
            raise bad(f"id «{item['id']}» finnes to ganger")
        ids.add(item["id"])
    return plan


def _same_rects(a: list[list[float]], b: list[list[float]]) -> bool:
    if len(a) != len(b):
        return False
    return all(
        abs(x - y) <= RECT_TOLERANCE for ra, rb in zip(a, b) for x, y in zip(ra, rb)
    )


def _match_plan(plan: dict[str, Any], hits: list[Hit], name: str) -> tuple[list[Hit], list[Hit]]:
    """Map plan items to freshly detected hits. Returns (to_redact, kept).

    The plan and the detection must agree one to one: every item must be a
    hit detection finds in this very PDF (same type, text, page, placement
    and rectangles), and every hit must have an item. Striking is done with
    "sladd": false. Anything else (an item added, changed or deleted, or the
    term list changed) means the plan no longer matches, and we refuse.
    """
    used: set[int] = set()
    to_redact: list[Hit] = []
    kept: list[Hit] = []
    for item in plan["treff"]:
        match = None
        for i, hit in enumerate(hits):
            if i in used:
                continue
            if (
                hit.type == item["type"]
                and hit.text == item["tekst"]
                and hit.page == item["side"]
                and hit.placement == item["plassering"]
                and hit.rejected == item.get("forkastet", False)
                and _same_rects(hit.plan_rects(), item["rektangler"])
            ):
                match = i
                break
        if match is None:
            raise UserError(
                _BAD_PLAN.format(
                    name=name,
                    why=(
                        f"treff «{item['id']}» ({TYPE_LABELS[item['type']]}, side "
                        f"{item['side']}) finnes ikke i PDF-en slik planen beskriver det"
                    ),
                )
            )
        used.add(match)
        (to_redact if item["sladd"] else kept).append(hits[match])
    missing = [h for i, h in enumerate(hits) if i not in used]
    if missing:
        first = missing[0]
        where = f"side {first.page}" if first.page else first.placement
        raise UserError(
            _BAD_PLAN.format(
                name=name,
                why=(
                    f"{len(missing)} treff i PDF-en mangler i planen (først: "
                    f"{TYPE_LABELS[first.type]} på {where}). Treff strykes med "
                    "\"sladd\": false, ikke ved å slette dem. Er listen «termer» "
                    "endret, må planen lages på nytt"
                ),
            )
        )
    return to_redact, kept


# --------------------------------------------------------------------- redact


@dataclass
class RedactResult:
    output_path: Path
    redacted: list[Hit]
    kept: list[Hit]
    warnings: list[str] = field(default_factory=list)
    left_rejected: list[Hit] = field(default_factory=list)
    hits_found: int = 0


class VerificationError(UserError):
    """The finished file still contained redacted data. No file was written."""


def _value(hit: Hit) -> Value:
    return Value(hit.type, norm_text(hit.text))


# Catalog and page keys that are kept. Everything else is removed: outline,
# names (destinations, JavaScript, attachments), actions, structure tree,
# metadata, page labels, layers, private keys, ...
CATALOG_KEEP = {
    "Type", "Pages", "Version", "Extensions", "PageLayout",
    "ViewerPreferences", "Lang", "OutputIntents",
}
PAGE_KEEP = {
    "Type", "Parent", "Resources", "MediaBox", "CropBox", "BleedBox", "TrimBox",
    "ArtBox", "Contents", "Rotate", "Group", "UserUnit",
}
# Removed from every object (private application data, per-object metadata).
ANY_DROP = ("PieceInfo", "Metadata", "LastModified", "StructParent", "StructParents")


def _strip_keys(doc: pymupdf.Document, xref: int, keep: set[str]) -> None:
    """Rewrite the dictionary with only the kept keys (setting a key to
    null leaves "/Key null" behind; this removes it)."""
    parts = []
    for key in doc.xref_get_keys(xref):
        if key not in keep:
            continue
        kind, value = doc.xref_get_key(xref, key)
        if kind == "null":
            continue
        if kind == "string":
            value = pymupdf.get_pdf_str(value)
        parts.append(f"/{key} {value}")
    doc.update_object(xref, "<<" + " ".join(parts) + ">>")


def _strip_document_level(doc: pymupdf.Document) -> None:
    """Remove everything that is not page content and can carry text."""
    doc.scrub(
        attached_files=True,
        clean_pages=True,
        embedded_files=True,
        hidden_text=False,  # would delete a legitimate OCR text layer
        javascript=True,
        metadata=True,
        redactions=False,  # already applied, with our options
        remove_links=True,
        reset_fields=True,
        reset_responses=True,
        thumbnails=True,
        xml_metadata=True,
    )
    for name in list(doc.embfile_names()):
        doc.embfile_del(name)
    doc.set_toc([])
    doc.set_metadata({})
    doc.del_xml_metadata()
    _strip_keys(doc, doc.pdf_catalog(), CATALOG_KEEP)
    for page in doc:
        _strip_keys(doc, page.xref, PAGE_KEEP)
    for xref in range(1, doc.xref_length()):
        try:
            keys = set(doc.xref_get_keys(xref))
        except Exception:  # noqa: BLE001 - free entry
            continue
        for key in ANY_DROP:
            if key in keys:
                doc.xref_set_key(xref, key, "null")
    # Info dictionary: drop the trailer reference entirely
    if doc.xref_get_key(-1, "Info")[0] != "null":
        doc.xref_set_key(-1, "Info", "null")


def redact_with_plan(
    input_path: Path,
    plan_path: Path,
    out_dir: Path,
    progress: Progress = None,
) -> RedactResult:
    plan = load_plan(plan_path)
    actual = sha256_file(input_path) if input_path.is_file() else None
    _open_pdf(input_path).close()  # readable PDF? (Norwegian errors)
    if actual != plan["kilde"]["sha256"]:
        raise UserError(
            f"Planen «{plan_path.name}» hører ikke til «{input_path.name}»: "
            "SHA-256 stemmer ikke. PDF-en er endret eller det er feil plan. "
            "Kjør «jv redact finn» på nytt for denne filen."
        )
    terms = plan["termer"]

    def step(x: float) -> None:
        if progress:
            progress(x)

    work = _open_working(input_path)
    doc = work.doc
    try:
        warnings = _check_text_layer(work, input_path.name)
        hits, _extra = _collect_hits(input_path, work, terms)
        quiet = [h for h in hits if h.quiet]
        hits = [h for h in hits if not h.quiet]
        to_redact, kept = _match_plan(plan, hits, plan_path.name)
        # Nothing marked: still deliver a cleaned copy (metadata, outline,
        # links ... removed, post-check run), with a clear summary.
        step(0.1)

        before = extract_all(doc, doc.tobytes(garbage=0))
        step(0.25)

        page_hits = [h for h in to_redact if h.placement in PAGE_PLACEMENTS]
        pages = sorted({h.page for h in page_hits})
        for h in page_hits:
            page = doc[h.page - 1]
            for r in h.rects:
                page.add_redact_annot(pymupdf.Rect(r), fill=(0, 0, 0))
        if not to_redact:
            warnings.append(NOTHING_MARKED)
        for n, page_no in enumerate(pages, 1):
            doc[page_no - 1].apply_redactions(**REDACT_OPTIONS)
            step(0.25 + 0.35 * n / len(pages))

        _strip_document_level(doc)
        restore_boxes(doc, work.original_boxes)
        data = doc.tobytes(
            garbage=4,
            clean=True,
            deflate=True,
            incremental=False,
            encryption=pymupdf.PDF_ENCRYPT_NONE,
        )
    finally:
        doc.close()
    step(0.7)

    left_rejected = [h for h in kept if h.rejected]
    kept = [h for h in kept if not h.rejected]
    left_rejected_all = left_rejected + quiet
    kept_page = [h for h in kept if h.placement in PAGE_PLACEMENTS]
    kept_values = {_value(h) for h in kept_page}
    redacted_pairs = [(_value(h), h.page) for h in page_hits]
    fully = {_value(h) for h in to_redact if _value(h) not in kept_values}
    findings, verify_warnings = verify(
        data,
        before,
        redacted_pairs,
        fully,
        kept=[Kept(h.type, h.normalized, h.page) for h in kept_page],
        rejected=[
            RejectedLeft(r.type, r.normalized, r.page, tuple(tuple(x) for x in r.rects))
            for r in left_rejected_all
        ],
        terms=terms,
    )
    warnings += verify_warnings
    step(0.95)
    if findings:
        raise VerificationError(
            "Etterkontrollen fant personopplysninger som fortsatt kan hentes ut, "
            "så ingen fil er laget:\n  - " + "\n  - ".join(findings)
        )

    if left_rejected:
        warnings.append(REJECT_LEFT.format(n=len(left_rejected)))
    if quiet:
        warnings.append(
            f"{len(quiet)} tallrekker med dato (firesifret år), saksnummer eller beløp med to "
            "desimaler fra nabokolonner er ikke i planen og står igjen i dokumentet. De består kontrollsifrene for "
            "fødselsnummer ved tilfeldighet; les gjennom dokumentet selv."
        )
    if kept_page:
        warnings.append(
            f"{len(kept_page)} treff ble strøket fra planen og står igjen i dokumentet "
            f"({count_by_type(kept_page)})."
        )
    kept_other = [h for h in kept if h.placement not in PAGE_PLACEMENTS]
    if kept_other:
        warnings.append(
            f"{len(kept_other)} strøkne treff i bokmerker, lenker, sidelabels eller "
            "metadata er fjernet likevel, fordi disse alltid fjernes."
        )
    for v in sorted(kept_values & {v for v, _ in redacted_pairs}, key=lambda v: v.text):
        warnings.append(
            f"{v.label()} er sladdet noen steder og strøket andre steder, så den "
            "finnes fortsatt i dokumentet der den ble strøket."
        )

    out = safe_output_path(input_path, out_dir, "-sladdet.pdf")
    with open(out, "xb") as fh:
        fh.write(data)
    step(1.0)
    return RedactResult(out, to_redact, kept, warnings, left_rejected, len(hits))
