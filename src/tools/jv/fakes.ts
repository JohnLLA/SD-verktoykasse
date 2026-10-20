// En falsk kjerne til tester og prøvevisning: samme grensesnitt som Rust-modulen,
// men uten Tauri. Testene styrer hendelsene selv (`emit*`).

import type {
  CatalogEntry,
  CatalogView,
  InstallDoneEvent,
  InstallProgressEvent,
  InstalledView,
  JvError,
  JvJobId,
  PlanView,
  RunDoneEvent,
  RunProgressEvent,
  RunRequest,
  ToolStatus,
  ToolView,
} from "./api";
import { JV_TOOL_IDS } from "./api";
import type { JvBackend, JvBackendEvents } from "./backend";
import type { Platform } from "../../platform/types";
import { MemorySettings } from "../../lib/settings";

export function entry(id: string, over: Partial<CatalogEntry> = {}): CatalogEntry {
  return {
    id,
    name: id,
    version: "1.0.0",
    target: "aarch64-apple-darwin",
    url: "https://github.com/JohnLLA/sd-verktoy-releases/releases/download/x/y.tar.gz",
    bytes: 120_000_000,
    sha256: "0".repeat(64),
    min_app_version: "0.1.0",
    min_os: null,
    notes: "",
    ...over,
  };
}

export function toolView(id: string, status: ToolStatus, over: Partial<ToolView> = {}): ToolView {
  return {
    id,
    status,
    entry: status === "not_for_platform" || status === "unknown" ? null : entry(id),
    installed_version: null,
    update_available: false,
    ...over,
  };
}

export function catalogOf(views: Partial<Record<string, ToolStatus | ToolView>>, over: Partial<CatalogView> = {}): CatalogView {
  return {
    target: "aarch64-apple-darwin",
    source: "network",
    error: null,
    tools: JV_TOOL_IDS.map((id) => {
      const v = views[id];
      if (v && typeof v === "object") return v;
      return toolView(id, v ?? "available");
    }),
    ...over,
  };
}

export class FakeJvBackend implements JvBackend {
  handlers: JvBackendEvents | null = null;
  nextJob = 1;
  calls: { name: string; args: unknown[] }[] = [];

  catalogResult: CatalogView | JvError = catalogOf({});
  installedList: InstalledView[] = [];
  installError: JvError | null = null;
  runError: JvError | null = null;
  plan: PlanView = { items: [] };
  savedPlans: { path: string; redact: Record<string, boolean> }[] = [];
  savePlanError: JvError | null = null;

  private log(name: string, ...args: unknown[]): void {
    this.calls.push({ name, args });
  }
  callsOf(name: string): unknown[][] {
    return this.calls.filter((c) => c.name === name).map((c) => c.args);
  }

  async catalog(fetch: boolean): Promise<CatalogView> {
    this.log("catalog", fetch);
    if ("code" in this.catalogResult) throw this.catalogResult;
    return this.catalogResult;
  }
  async installed(): Promise<InstalledView[]> {
    this.log("installed");
    return this.installedList;
  }
  async install(id: string): Promise<JvJobId> {
    this.log("install", id);
    if (this.installError) throw this.installError;
    return this.nextJob++;
  }
  async remove(id: string): Promise<void> {
    this.log("remove", id);
    this.installedList = this.installedList.filter((i) => i.id !== id);
  }
  async run(id: string, request: RunRequest): Promise<JvJobId> {
    this.log("run", id, request);
    if (this.runError) throw this.runError;
    return this.nextJob++;
  }
  async cancel(jobId: JvJobId): Promise<void> {
    this.log("cancel", jobId);
  }
  async readPlan(path: string): Promise<PlanView> {
    this.log("readPlan", path);
    return JSON.parse(JSON.stringify(this.plan)) as PlanView;
  }
  async savePlan(path: string, redact: Record<string, boolean>): Promise<void> {
    this.log("savePlan", path, redact);
    if (this.savePlanError) throw this.savePlanError;
    this.savedPlans.push({ path, redact });
  }
  async listen(h: JvBackendEvents): Promise<() => void> {
    this.handlers = h;
    return () => {
      this.handlers = null;
    };
  }

  // ---- hendelser
  installProgress(ev: Omit<InstallProgressEvent, "phase"> & { phase?: InstallProgressEvent["phase"] }): void {
    this.handlers?.installProgress({ phase: "download", ...ev });
  }
  installDone(ev: Partial<InstallDoneEvent> & { job_id: number; id: string }): void {
    this.handlers?.installDone({ outcome: "completed", error: null, version: "1.0.0", ...ev });
  }
  runProgress(ev: RunProgressEvent): void {
    this.handlers?.runProgress(ev);
  }
  runDone(ev: Partial<RunDoneEvent> & { job_id: number; id: string }): void {
    this.handlers?.runDone({ outcome: "completed", error: null, message: null, report: null, ...ev });
  }
}

/** `Platform` til tester: alt er stumt, og valgene styres av testen. */
export function fakePlatform(over: Partial<Platform> = {}): Platform {
  return {
    os: "mac",
    settings: new MemorySettings(),
    pickFiles: async () => [],
    pickFolder: async () => null,
    pickSavePath: async () => null,
    onDrop: async () => () => undefined,
    playbackUrl: async () => null,
    reveal: async () => undefined,
    copyText: async () => true,
    appVersion: async () => "0.1.0",
    checkForUpdate: async () => null,
    checkForUpdateNow: async () => ({ status: "none" }),
    installUpdate: async () => true,
    onCloseRequested: async () => () => undefined,
    ...over,
  };
}
