import { describe, expect, it } from "vitest";
import { DownloadTracker } from "./download";

const progress = (job_id: number, downloaded: number, total = 1000) => ({
  job_id,
  model_id: "m",
  downloaded,
  total,
});
const done = (job_id: number, outcome: "completed" | "cancelled" | "failed", error = null as null | { code: "network" }) => ({
  job_id,
  model_id: "m",
  outcome,
  error,
});

describe("DownloadTracker", () => {
  it("følger en nedlasting fra start til ferdig", () => {
    const d = new DownloadTracker();
    d.begin("m", 250);
    expect(d.state?.downloaded).toBe(250); // gjenopptar
    expect(d.active).toBe(true);
    d.attach(1);
    d.progress(progress(1, 400));
    expect(d.state?.downloaded).toBe(400);
    expect(d.state?.total).toBe(1000);
    d.done(done(1, "completed"));
    expect(d.state?.status).toBe("done");
    expect(d.active).toBe(false);
  });

  it("samler hendelser som kommer før jobb-ID-en er kjent", () => {
    const d = new DownloadTracker();
    d.begin("m");
    d.progress(progress(2, 300));
    d.done(done(2, "failed", { code: "network" }));
    d.attach(2);
    expect(d.state?.status).toBe("failed");
    expect(d.state?.error).toEqual({ code: "network" });
  });

  it("holder fast på nedlastingen som ble forkastet ved avbrudd", () => {
    const d = new DownloadTracker();
    d.begin("m");
    d.attach(3);
    expect(d.requestCancel()).toBe(3);
    d.done(done(3, "cancelled"));
    expect(d.state?.status).toBe("cancelled");
    expect(d.state?.error).toBeNull();
  });

  it("husker Avbryt som ble trykket før jobb-ID var kjent", () => {
    const d = new DownloadTracker();
    d.begin("m");
    expect(d.requestCancel()).toBeNull();
    expect(d.attach(4)).toBe(true);
  });

  it("feil ved start gir feilet med feilen, eller avbrutt", () => {
    const d = new DownloadTracker();
    d.begin("m");
    d.fail({ code: "already_downloading" });
    expect(d.state?.status).toBe("failed");
    d.begin("m");
    d.fail({ code: "cancelled" });
    expect(d.state?.status).toBe("cancelled");
  });

  it("ignorerer hendelser fra andre jobber", () => {
    const d = new DownloadTracker();
    d.begin("m");
    d.attach(5);
    d.progress(progress(9, 999));
    expect(d.state?.downloaded).toBe(0);
  });
});
