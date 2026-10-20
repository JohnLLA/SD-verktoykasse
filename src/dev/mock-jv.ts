// Prøvevisning av journalistverktøyene uten Tauri (bare under utvikling, se
// `mock.ts`). Etterligner Rust-modulen jv med oppdiktede kataloger, tidsforløp
// og rapporter, så alle tilstander i grensesnittet kan sees og prøves.
// Ingen filnavn eller tekst skrives til konsollen.
//
// Styres med adressen (sammen med parameterne i `mock.ts`):
//   verktoy  = kommaliste med id-er som er lastet ned, `alle` eller `ingen`
//              (standard: compare,redact)
//   os       = windows: katalogen har ingen Windows-linjer («Kommer for Windows»)
//   macos    = gammel: ocr, metadata, keyframes og loudness krever nyere macOS
//   nedlasting = feil (stopper med «ingen nett» midt i) | treg | skadet
//   kjoring  = feil | treg | hurtig | advarsel
//   verktoyoppdatering = ny: subtitles har ny versjon i katalogen
//   nett     = nede: katalogen kan ikke hentes

import type { JvBackend, JvBackendEvents } from "../tools/jv/backend";
import type {
  CatalogEntry,
  CatalogView,
  InstalledView,
  JvError,
  JvJobId,
  JvReport,
  PlanItem,
  PlanView,
  RunRequest,
  ToolView,
} from "../tools/jv/api";
import { JV_TOOL_IDS } from "../tools/jv/api";

const params = new URLSearchParams(location.search);
const param = (k: string, d: string) => params.get(k) ?? d;

const NAMES: Record<string, string> = {
  compare: "Sammenlign versjoner",
  metadata: "Metadata – vis og fjern",
  keyframes: "Stillbilder fra video",
  loudness: "Lydnivå",
  subtitles: "Teksting",
  "pdf-tables": "Tabeller fra PDF",
  ocr: "Søkbare PDF-er (OCR)",
  redact: "Sladding av PDF",
  nynorsk: "Bokmål ↔ nynorsk",
};

const SIZES: Record<string, number> = {
  compare: 61_000_000,
  metadata: 94_000_000,
  keyframes: 118_000_000,
  loudness: 117_000_000,
  subtitles: 58_000_000,
  "pdf-tables": 143_000_000,
  ocr: 211_000_000,
  redact: 152_000_000,
  nynorsk: 187_000_000,
};

const MIN_OS: Record<string, string> = { ocr: "26.6.2", metadata: "15", keyframes: "26", loudness: "26" };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const base = (p: string) => p.split(/[\\/]/).pop() ?? p;
const dir = (p: string) => p.slice(0, Math.max(p.lastIndexOf("/"), 0)) || "/";
const stem = (p: string) => base(p).replace(/\.[^.]+$/, "");

function installedSet(): Set<string> {
  const v = param("verktoy", "compare,redact");
  if (v === "alle") return new Set(JV_TOOL_IDS);
  if (v === "ingen" || v === "") return new Set();
  return new Set(v.split(","));
}

function plan(): PlanItem[] {
  const hit = (n: number, type: string, page: number, excerpt: string, over: Partial<PlanItem> = {}): PlanItem => ({
    id: `t${n}`,
    type,
    page,
    excerpt,
    placement: "side",
    redact: true,
    rejected: false,
    reason: null,
    ...over,
  });
  return [
    hit(1, "fodselsnummer", 1, "…søkeren (fødselsnummer 150685 27101) har oppgitt…"),
    hit(2, "fodselsnummer", 2, "…barnet, født 29.02.92, fnr 290292 41803…"),
    hit(3, "telefon", 2, "…kan nås på telefon 58 01 23 45 eller…"),
    hit(4, "epost", 3, "…send svar til kari.fiktivsen@eksempel.no innen…"),
    hit(5, "term", 3, "…saken gjelder Kari Fiktivsen og hennes…"),
    hit(6, "term", 4, "…Fiktivsen-saken ble behandlet i…", { placement: "skjult lag" }),
    hit(7, "telefon", 5, "…Sum 4 581 2345 kr i kolonne tre…", { redact: false, rejected: true, reason: "avstand" }),
    hit(8, "fodselsnummer", 6, "…saksnr 2026 150685 27101 i tabell…", { redact: false, rejected: true, reason: "avstand" }),
  ];
}

function reportFor(id: string, req: RunRequest): JvReport {
  const first = req.inputs[0] ?? "/Users/kari/Saker/fil";
  const out = req.out_dir ?? dir(first);
  const warn = param("kjoring", "") === "advarsel";
  const o = (name: string) => `${out}/${name}`;
  switch (id) {
    case "compare":
      return {
        summary: "Fant 14 endrede avsnitt: 212 ord lagt til og 187 ord fjernet.",
        warnings: warn ? ["Den gamle versjonen er en PDF uten tekstlag. Kjør «Søkbare PDF-er» først."] : [],
        outputs: [o(`${stem(first)}-sammenligning.html`)],
      };
    case "metadata":
      if (req.command === "vis") {
        return {
          summary: `Leste metadata fra ${req.inputs.length === 1 ? "1 fil" : `${req.inputs.length} filer`}: 9 felt, 4 følsomme (sted eller person).`,
          warnings: warn ? ["Hoppet over «notater.tmp»: filtypen støttes ikke."] : [],
          outputs: req.inputs.map((p) => ({
            path: p,
            format: "JPEG",
            field_count: 9,
            sensitive_count: 4,
            groups: {
              Sted: [
                { field: "GPSLatitude", source: "exif", value: "60,3913 N", group: "Sted", sensitive: true },
                { field: "GPSLongitude", source: "exif", value: "5,3221 Ø", group: "Sted", sensitive: true },
              ],
              Person: [
                { field: "Artist", source: "exif", value: "Ola Testesen", group: "Person", sensitive: true },
                { field: "OwnerName", source: "exif", value: "Redaksjonen", group: "Person", sensitive: true },
              ],
              Utstyr: [
                { field: "Make", source: "exif", value: "Apple", group: "Utstyr", sensitive: false },
                { field: "Model", source: "exif", value: "iPhone 15", group: "Utstyr", sensitive: false },
              ],
              Tid: [{ field: "DateTimeOriginal", source: "exif", value: "2026:10:12 14:03:11", group: "Tid", sensitive: false }],
              Annet: [{ field: "Orientation", source: "exif", value: "Rotert 90°", group: "Annet", sensitive: false }],
            },
          })),
        };
      }
      return {
        summary: `Lagde vasket kopi av ${req.inputs.length === 1 ? "1 fil" : `${req.inputs.length} filer`}. Kontrollen fant ingen følsomme felt igjen.`,
        warnings: [],
        outputs: req.inputs.map((p) => ({ path: o(`${stem(p)}-vasket.${base(p).split(".").pop()}`), verified: true })),
      };
    case "keyframes":
      return {
        summary: "Trakk ut 42 bilder fra 1 video (1 min 24 s, 1920×1080). SHA-256 for videoen står i rapporten.",
        warnings: [],
        outputs: [o(`${stem(first)}-kontaktark.jpg`), o("000000.000.jpg"), o("000002.000.jpg"), o("000004.000.jpg")],
      };
    case "loudness":
      return {
        summary: "Lydnivået er satt til −16 LUFS (før: −27,4 LUFS). Høyeste topp er −1,2 dBTP.",
        warnings: [],
        outputs: [o(`${stem(first)}-normalisert.${base(first).split(".").pop()}`)],
      };
    case "subtitles":
      return {
        summary: "Laget 38 undertekster. Ingen linje er lenger enn 42 tegn.",
        warnings: warn ? ["2 tekster er kortere enn ett sekund og ble slått sammen med nabotekstene."] : [],
        outputs: [o(`${stem(first)}.srt`), o(`${stem(first)}.vtt`)],
      };
    case "pdf-tables":
      return {
        summary: "Fant 3 tabeller på 5 sider. Tall i norsk format er lagret som tall.",
        warnings: ["Tabell 2 på side 4 har ujevnt antall kolonner."],
        outputs: [o(`${stem(first)}-tabeller.xlsx`)],
      };
    case "ocr":
      return {
        summary: "Gjorde 7 av 8 sider søkbare. 1 side hadde tekst fra før og ble hoppet over.",
        warnings: ["Side 3 har lav sikkerhet (gjennomsnittlig ordsikkerhet 48). Les gjennom den siden selv."],
        outputs: [o(`${stem(first)}-ocr.pdf`)],
      };
    case "redact":
      if (req.command === "finn") {
        return {
          summary: "Fant 6 treff (2 fødselsnummer, 1 telefonnummer, 1 e-postadresse, 2 egne ord). 2 mulige fødselsnumre/telefonnumre ble forkastet. Gå gjennom listen.",
          warnings: [
            "2 mulige fødselsnumre/telefonnumre ble IKKE merket for sladding (stor avstand mellom sifrene) – gå gjennom planen.",
            "1 treff ligger ikke som synlig tekst på siden (se «plassering» i planen).",
          ],
          outputs: [{ path: o(`${stem(first)}-treff.json`), treff: 6, forkastet: 2 }],
        };
      }
      return {
        summary: "Sladdet 7 treff (2 fødselsnummer, 1 telefonnummer, 1 e-postadresse, 2 egne ord, 1 forkastet). Etterkontrollen fant ingen av de sladdede verdiene igjen.",
        warnings: [],
        outputs: [{ path: o(`${stem(first)}-sladdet.pdf`), sladdet: 7 }],
      };
    default:
      return {
        summary: "Oversatte teksten til nynorsk. 3 ord ble ikke kjent og er merket med *.",
        warnings: ["3 ukjente ord: kommunestyremøte, utbyggingsavtale, fylkesveg. Sjekk dem selv."],
        outputs: [o(`${stem(first)}.nynorsk.${base(first).split(".").pop()}`)],
      };
  }
}

export class MockJvBackend implements JvBackend {
  private handlers: JvBackendEvents | null = null;
  private nextJob = 1;
  private have = installedSet();
  private versions = new Map<string, string>();
  private timers = new Map<JvJobId, number>();
  private fetched = false;

  private entry(id: string): CatalogEntry {
    const v = id === "subtitles" && param("verktoyoppdatering", "") === "ny" ? "1.1.0" : "1.0.0";
    return {
      id,
      name: NAMES[id] ?? id,
      version: v,
      target: param("os", "mac") === "windows" ? "x86_64-pc-windows-msvc" : "aarch64-apple-darwin",
      url: "https://github.com/JohnLLA/sd-verktoy-releases/releases/download/jv/pakke",
      bytes: SIZES[id] ?? 100_000_000,
      sha256: "0".repeat(64),
      min_app_version: "0.1.0",
      min_os: param("os", "mac") === "windows" ? null : (MIN_OS[id] ?? null),
      notes: "",
    };
  }

  async catalog(fetch: boolean): Promise<CatalogView> {
    const windows = param("os", "mac") === "windows";
    const old = param("macos", "") === "gammel";
    const down = param("nett", "") === "nede";
    if (fetch) {
      await sleep(700);
      if (down && !this.fetched) throw { code: "download", cause: { code: "network" } } satisfies JvError;
      if (!down) this.fetched = true;
    }
    const known = this.fetched || !fetch;
    const tools: ToolView[] = JV_TOOL_IDS.map((id) => {
      const have = this.have.has(id) ? (this.versions.get(id) ?? "1.0.0") : null;
      if (windows) return { id, status: "not_for_platform", entry: null, installed_version: have, update_available: false };
      const e = this.entry(id);
      const status = old && MIN_OS[id] ? "needs_newer_os" : "available";
      return { id, status, entry: e, installed_version: have, update_available: have !== null && have !== e.version };
    });
    if (!known && !this.fetched) {
      return { target: "aarch64-apple-darwin", source: "none", error: null, tools: tools.map((t) => ({ ...t, status: "unknown", entry: null })) };
    }
    return {
      target: windows ? "x86_64-pc-windows-msvc" : "aarch64-apple-darwin",
      source: fetch && !down ? "network" : "cache",
      error: fetch && down ? { code: "download", cause: { code: "network" } } : null,
      tools,
    };
  }

  private installedViews(): InstalledView[] {
    return [...this.have].map((id) => ({ id, name: NAMES[id] ?? id, version: this.versions.get(id) ?? "1.0.0", bytes: Math.round((SIZES[id] ?? 1e8) * 0.9), license: "AGPL-3.0-or-later" }));
  }

  async installed(): Promise<InstalledView[]> {
    return this.installedViews();
  }

  async install(id: string): Promise<JvJobId> {
    const job = this.nextJob++;
    const total = SIZES[id] ?? 1e8;
    const mode = param("nedlasting", "ok");
    let done = 0;
    const timer = window.setInterval(() => {
      done = Math.min(total, done + total / (mode === "treg" ? 400 : 40));
      this.handlers?.installProgress({ job_id: job, id, phase: "download", downloaded: Math.floor(done), total });
      if (mode === "feil" && done > total * 0.4) {
        window.clearInterval(timer);
        this.handlers?.installDone({ job_id: job, id, outcome: "failed", error: { code: "download", cause: { code: "network" } }, version: null });
      } else if (mode === "skadet" && done > total * 0.9) {
        window.clearInterval(timer);
        this.handlers?.installDone({ job_id: job, id, outcome: "failed", error: { code: "checksum_mismatch" }, version: null });
      } else if (done >= total) {
        window.clearInterval(timer);
        this.handlers?.installProgress({ job_id: job, id, phase: "install", downloaded: 0, total: 0 });
        window.setTimeout(() => {
          this.have.add(id);
          this.versions.set(id, this.entry(id).version);
          this.handlers?.installDone({ job_id: job, id, outcome: "completed", error: null, version: this.entry(id).version });
        }, 900);
      }
    }, 200);
    this.timers.set(job, timer);
    return job;
  }

  async remove(id: string): Promise<void> {
    this.have.delete(id);
    this.versions.delete(id);
  }

  async run(id: string, request: RunRequest): Promise<JvJobId> {
    const job = this.nextJob++;
    const mode = param("kjoring", "ok");
    const seconds = mode === "treg" ? 40 : mode === "hurtig" ? 0.6 : 5;
    const t0 = Date.now();
    const timer = window.setInterval(() => {
      const p = Math.min(1, (Date.now() - t0) / 1000 / seconds);
      this.handlers?.runProgress({ job_id: job, id, progress: p });
      if (p >= 1) {
        window.clearInterval(timer);
        if (mode === "feil") {
          this.handlers?.runDone({
            job_id: job,
            id,
            outcome: "failed",
            error: { code: "tool_failed", exit_code: 1 },
            message: `Filen «${base(request.inputs[0] ?? "fil")}» er skadet eller passordbeskyttet. Åpne den i et vanlig program først.`,
            report: null,
          });
        } else {
          this.handlers?.runDone({ job_id: job, id, outcome: "completed", error: null, message: null, report: reportFor(id, request) });
        }
      }
    }, 250);
    this.timers.set(job, timer);
    return job;
  }

  async cancel(jobId: JvJobId): Promise<void> {
    const timer = this.timers.get(jobId);
    if (timer !== undefined) window.clearInterval(timer);
    this.timers.delete(jobId);
    window.setTimeout(() => {
      // Vi vet ikke om det var en nedlasting eller en kjøring; begge lyttere ignorerer det de ikke eier.
      for (const id of JV_TOOL_IDS) {
        this.handlers?.installDone({ job_id: jobId, id, outcome: "cancelled", error: null, version: null });
        this.handlers?.runDone({ job_id: jobId, id, outcome: "cancelled", error: null, message: null, report: null });
      }
    }, 50);
  }

  async readPlan(): Promise<PlanView> {
    return { items: plan() };
  }

  async savePlan(): Promise<void> {}

  async listen(h: JvBackendEvents): Promise<() => void> {
    this.handlers = h;
    return () => {
      this.handlers = null;
    };
  }
}

export function createMockJv(): JvBackend {
  return new MockJvBackend();
}
