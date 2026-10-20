// Prøvevisning uten Tauri, bare under utvikling (`npm run dev` i nettleser).
// Etterligner kjernen med oppdiktet tekst og tidsforløp, så alle tilstander i
// grensesnittet kan sees og prøves uten modell og uten ekte lyd. Ingen av
// dette pakkes inn i den ferdige appen (`main.ts` laster det bare i DEV, og
// bare utenfor Tauri). Ingen filnavn eller tekst skrives til konsollen.
//
// Styres med adressen, f.eks. `http://localhost:1420/?modeller=ingen&tid=40`:
//   modeller = standard (medium tolket og small lydrett finnes) | ingen | alle
//   tid      = antall sekunder en transkribering varer (standard 12)
//   minne    = GB minne maskinen melder (standard 16)
//   cpu      = nei: prosessoren mangler AVX2
//   nedlasting = feil: nedlasting stopper med «ingen nett» midt i
//   os       = windows | mac
// Journalistverktøyene har egne parametere, se `mock-jv.ts`.
// `window.__mock.drop(["/mappe/fil.mp3"])` etterligner at filer slippes i vinduet.

import catalog from "../../models.json";
import type { Backend, BackendEvents } from "../tools/transkribering/backend";
import type {
  Choice,
  CoreError,
  ExportRequest,
  JobId,
  Kvalitet,
  Malform,
  ModelList,
  ModelStatus,
  Segment,
  Stil,
  SystemInfo,
  TranscribeRequest,
} from "../tools/transkribering/api";
import { setJvBackend } from "../tools/jv/backend";
import { setBackend } from "../tools/transkribering/backend";
import { createMockJv } from "./mock-jv";
import { MemorySettings } from "../lib/settings";
import type { Platform } from "../platform/types";
import type { Os } from "../lib/platform-info";

const params = new URLSearchParams(location.search);
const param = (k: string, d: string) => params.get(k) ?? d;

const SENTENCES_TOLKET = [
  "God morgen, og takk for at du tok deg tid til å møte oss.",
  "Kommunestyret vedtok budsjettet i går kveld, etter en lang debatt.",
  "Vi har ventet på dette i mange år, og nå er det endelig på plass.",
  "Veien over fjellet blir stengt i to uker mens arbeidet pågår.",
  "Nei, jeg vil ikke si at det var uventet, men det var tøft.",
  "Det viktigste nå er at barna får et trygt tilbud i nærmiljøet.",
  "Vi kommer til å følge saken tett fram mot valget.",
  "Takk for praten, og lykke til videre.",
];
const SENTENCES_LYDRETT = [
  "ja god morgen og takk for at du eh tok deg tid til å møte oss",
  "kommunestyret vedtok budsjettet i går kveld etter ei lang debatt",
  "vi har venta på dette i mange år og nå e det endelig på plass",
  "vegen over fjellet blir stengt i to uker mens arbeidet pågår",
  "nei jeg vil ikke si at det var uventa men det var tøft",
  "det viktigste nå e at ungene får et trygt tilbud i nærmiljøet",
  "vi kommer til å følge saken tett fram mot valget",
  "takk for praten og lykke til videre",
];
const SENTENCES_NYNORSK = [
  "God morgon, og takk for at du tok deg tid til å møte oss.",
  "Kommunestyret vedtok budsjettet i går kveld, etter ei lang debatt.",
  "Vi har venta på dette i mange år, og no er det endeleg på plass.",
  "Vegen over fjellet blir stengd i to veker medan arbeidet pågår.",
  "Nei, eg vil ikkje seie at det var uventa, men det var tøft.",
  "Det viktigaste no er at borna får eit trygt tilbod i nærmiljøet.",
  "Vi kjem til å følgje saka tett fram mot valet.",
  "Takk for praten, og lukke til vidare.",
];

function sampleSegments(malform: Malform, stil: Stil, seconds: number): Segment[] {
  const base = malform === "nynorsk" ? SENTENCES_NYNORSK : stil === "lydrett" ? SENTENCES_LYDRETT : SENTENCES_TOLKET;
  const n = Math.max(4, Math.round(seconds / 6));
  return Array.from({ length: n }, (_, i) => ({
    start_ms: i * 6000,
    end_ms: i * 6000 + 5500,
    text: base[i % base.length] ?? "",
  }));
}

function buildCatalog(installed: Set<string>): ModelList {
  const variants = catalog.style_to_variant as Record<string, string>;
  const sizes = catalog.quality_to_size as Record<string, string>;
  const models: ModelStatus[] = catalog.models.map((m) => ({
    id: m.id,
    variant: m.variant as ModelStatus["variant"],
    size: m.size as ModelStatus["size"],
    quant: m.quant,
    repo: m.repo,
    bytes: m.bytes,
    installed: installed.has(m.id),
    location: installed.has(m.id) ? "app" : null,
    partial_bytes: 0,
  }));
  const choices: Choice[] = [];
  for (const stil of ["lydrett", "tolket"] as const) {
    for (const kvalitet of ["rask", "anbefalt", "best"] as const) {
      const found = models.find(
        (m) => m.variant === variants[stil] && m.size === sizes[kvalitet] && m.quant === catalog.default_quant,
      );
      if (found) choices.push({ stil, kvalitet, model_id: found.id });
    }
  }
  return {
    models,
    choices,
    app_model_dir: "/Users/kari/Library/Application Support/no.lla.verktoykasse/modeller",
    custom_model_dir: null,
    license: catalog.license,
    license_holder: catalog.license_holder,
  };
}

/** En stille tone på noen sekunder, så avspilleren har noe å spille. */
function toneUrl(seconds: number): string {
  const rate = 8000;
  const n = rate * seconds;
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const w = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF");
  v.setUint32(4, 36 + n * 2, true);
  w(8, "WAVEfmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  w(36, "data");
  v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    const beep = Math.floor(i / rate) % 6 === 0 ? Math.sin((2 * Math.PI * 440 * i) / rate) * 2500 : 0;
    v.setInt16(44 + i * 2, beep, true);
  }
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}

class MockBackend implements Backend {
  private handlers: BackendEvents | null = null;
  private nextJob = 1;
  private installed: Set<string>;
  private timers = new Map<JobId, number>();
  private written = new Set<string>();
  private customDir: string | null = null;
  private seconds = Number(param("tid", "12"));

  constructor() {
    const choice = param("modeller", "standard");
    const all = catalog.models.filter((m) => m.quant === catalog.default_quant).map((m) => m.id);
    this.installed = new Set(
      choice === "ingen"
        ? []
        : choice === "alle"
          ? all
          : ["nb-whisper-medium-q5_0", "nb-whisper-small-verbatim-q5_0"],
    );
  }

  async checkSystem(): Promise<SystemInfo> {
    const ok = param("cpu", "ja") !== "nei";
    return {
      cpu_supported: ok,
      missing_cpu_features: ok ? [] : ["avx2"],
      physical_cores: 8,
      whisper_threads: 6,
      total_memory_bytes: Number(param("minne", "16")) * 2 ** 30,
      accelerator: "metal",
    };
  }

  async listModels(): Promise<ModelList> {
    const list = buildCatalog(this.installed);
    list.custom_model_dir = this.customDir;
    return list;
  }

  async downloadModel(modelId: string): Promise<JobId> {
    const job = this.nextJob++;
    const total = catalog.models.find((m) => m.id === modelId)?.bytes ?? 1;
    let done = 0;
    const fail = param("nedlasting", "ok") === "feil";
    const id = window.setInterval(() => {
      done = Math.min(total, done + total / 40);
      this.handlers?.downloadProgress({ job_id: job, model_id: modelId, downloaded: Math.floor(done), total });
      if (fail && done > total * 0.4) {
        window.clearInterval(id);
        this.handlers?.downloadDone({ job_id: job, model_id: modelId, outcome: "failed", error: { code: "network" } });
      } else if (done >= total) {
        window.clearInterval(id);
        this.installed.add(modelId);
        this.handlers?.downloadDone({ job_id: job, model_id: modelId, outcome: "completed", error: null });
      }
    }, 250);
    this.timers.set(job, id);
    return job;
  }

  async deleteModel(modelId: string): Promise<void> {
    this.installed.delete(modelId);
  }

  async setModelDir(path: string | null): Promise<void> {
    this.customDir = path;
  }

  async transcribe(req: TranscribeRequest): Promise<JobId> {
    const job = this.nextJob++;
    const fail = /feil/i.test(req.audio_path);
    const kvalitetModel = (k: Kvalitet, s: Stil) =>
      buildCatalog(this.installed).choices.find((c) => c.kvalitet === k && c.stil === s)?.model_id ?? "";
    const model_id = kvalitetModel(req.kvalitet, req.stil);
    const segments = sampleSegments(req.malform, req.stil, 84);
    const t0 = Date.now();
    let emitted = 0;
    const id = window.setInterval(() => {
      const elapsed = (Date.now() - t0) / 1000;
      const percent = Math.min(100, (elapsed / this.seconds) * 100);
      if (elapsed > 1.2) {
        const remaining = Math.max(0, (this.seconds - elapsed) * 1000);
        this.handlers?.progress({ job_id: job, percent, eta_ms: remaining });
      }
      while (emitted < segments.length && (emitted / segments.length) * 100 <= percent && elapsed > 1.2) {
        const s = segments[emitted];
        if (s) this.handlers?.segment({ job_id: job, ...s });
        emitted++;
      }
      if (fail && percent > 30) {
        window.clearInterval(id);
        this.handlers?.done({
          job_id: job,
          outcome: "failed",
          error: { code: "decode_failed" },
          model_id,
          duration_ms: 0,
          segments: [],
        });
      } else if (percent >= 100) {
        window.clearInterval(id);
        this.handlers?.done({ job_id: job, outcome: "completed", error: null, model_id, duration_ms: 84_000, segments });
      }
    }, 300);
    this.timers.set(job, id);
    return job;
  }

  async cancel(jobId: JobId): Promise<void> {
    const timer = this.timers.get(jobId);
    if (timer !== undefined) window.clearInterval(timer);
    this.timers.delete(jobId);
    window.setTimeout(() => {
      this.handlers?.done({ job_id: jobId, outcome: "cancelled", error: null, model_id: "", duration_ms: 0, segments: [] });
      this.handlers?.downloadDone({ job_id: jobId, model_id: "", outcome: "cancelled", error: null });
    }, 50);
  }

  async suggestExportPath(audioPath: string, malform: Malform, stil: Stil, format: string): Promise<string> {
    const stem = audioPath.replace(/\.[^./\\]+$/, "");
    return `${stem}.${malform === "bokmål" ? "bokmal" : "nynorsk"}.${stil}.${format}`;
  }

  async exportFile(req: ExportRequest): Promise<string> {
    const path = req.target_path ?? (await this.suggestExportPath(req.audio_path, req.malform, req.stil, req.format));
    if (this.written.has(path) && !req.overwrite) {
      const e: CoreError = { code: "file_exists" };
      throw e;
    }
    this.written.add(path);
    return path;
  }

  async listen(h: BackendEvents): Promise<() => void> {
    this.handlers = h;
    return () => {
      this.handlers = null;
    };
  }
}

function mockOs(): Os {
  const o = param("os", "");
  if (o === "windows" || o === "mac") return o;
  return /Windows/i.test(navigator.userAgent) ? "windows" : "mac";
}

export async function installMock(): Promise<Platform> {
  setBackend(new MockBackend());
  setJvBackend(createMockJv());
  const settings = new MemorySettings();
  const dropHandlers = new Set<{ onFiles(p: string[]): void; onHover(o: boolean): void }>();
  let url: string | null = null;

  const platform: Platform = {
    os: mockOs(),
    settings,
    async pickFiles(opts) {
      const ext = opts?.extensions?.[0] ?? "mp3";
      if (ext === "mp3") return ["/Users/kari/Intervjuer/Ordfører og ny skole.mp3"];
      // Journalistverktøyene: en passende fil (to for sammenligning).
      if (opts.extensions.includes("docx") && opts.extensions.includes("pdf")) {
        return ["/Users/kari/Saker/Vedtak utkast 1.docx", "/Users/kari/Saker/Vedtak utkast 2.docx"];
      }
      return [`/Users/kari/Saker/Innsyn bygdebok.${ext}`];
    },
    async pickFolder() {
      return "/Volumes/Redaksjonen/Delte modeller";
    },
    async pickSavePath(o) {
      return o.defaultPath;
    },
    async onDrop(h) {
      dropHandlers.add(h);
      return () => {
        dropHandlers.delete(h);
      };
    },
    async playbackUrl() {
      url ??= toneUrl(90);
      return url;
    },
    async reveal() {},
    async copyText(text) {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        // Nettleseren kan nekte; prøvevisningen later som det gikk bra.
      }
      return true;
    },
    async appVersion() {
      return "0.1.0";
    },
    // ?oppdatering=ny viser varselet; ?oppdatering=feil lar installasjonen mislykkes.
    async checkForUpdate() {
      return param("oppdatering", "") === "" ? null : "0.2.0";
    },
    async checkForUpdateNow() {
      await new Promise((r) => setTimeout(r, 600));
      const v = param("oppdatering", "");
      return v === "" ? ({ status: "none" } as const) : v === "nett" ? ({ status: "failed" } as const) : ({ status: "available", version: "0.2.0" } as const);
    },
    async installUpdate() {
      await new Promise((r) => setTimeout(r, 1500));
      return param("oppdatering", "") !== "feil";
    },
    async onCloseRequested() {
      return () => undefined;
    },
  };

  (window as unknown as { __mock: unknown }).__mock = {
    drop: (paths: string[]) => dropHandlers.forEach((h) => h.onFiles(paths)),
    hover: (over: boolean) => dropHandlers.forEach((h) => h.onHover(over)),
  };
  return platform;
}
