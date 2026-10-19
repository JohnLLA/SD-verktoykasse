// SPDX-License-Identifier: AGPL-3.0-or-later
//! Tauri-kommandoene og -hendelsene for journalistverktøyene.
//!
//! Kommandoer (kalles som `plugin:jv|<navn>`):
//!
//! | Kommando | Inn | Ut |
//! |---|---|---|
//! | `jv_catalog` | `fetch` (bool) | [`CatalogView`]. `fetch=false`: bare siste kontrollerte kopi, ingen nett |
//! | `jv_installed` | – | liste med [`InstalledView`] |
//! | `jv_install` | `id` | jobb-ID; hendelser `install-progress`/`install-done` |
//! | `jv_remove` | `id` | – |
//! | `jv_run` | `id`, `request` ([`RunRequest`]) | jobb-ID; hendelser `run-progress`/`run-done` |
//! | `jv_cancel` | `job_id` | – |
//!
//! Hendelser (`jv:<navn>`), alle med `job_id` og `id`:
//! `install-progress {phase, downloaded, total}`, `install-done {outcome, error, version}`,
//! `run-progress {progress}`, `run-done {outcome, error, message, report}`.
//! `report` er verktøyets JSON-rapport (bare ved kode 0); `message` er verktøyets
//! norske feilmelding ved kode 1.
//!
//! Feil er [`JvError`] (`{"code": ...}`). Ingenting her logger (regel 2).

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, Runtime, State};

use super::args::RunRequest;
use super::error::JvError;
use super::runner::{self, Finished};
use super::service::{CatalogView, InstallPhase, InstalledView, JobId, Jv};

pub const EV_INSTALL_PROGRESS: &str = "jv:install-progress";
pub const EV_INSTALL_DONE: &str = "jv:install-done";
pub const EV_RUN_PROGRESS: &str = "jv:run-progress";
pub const EV_RUN_DONE: &str = "jv:run-done";

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Completed,
    Cancelled,
    Failed,
}

#[derive(Serialize, Clone)]
struct InstallProgressEvent<'a> {
    job_id: JobId,
    id: &'a str,
    phase: InstallPhase,
    downloaded: u64,
    total: u64,
}

#[derive(Serialize, Clone)]
struct InstallDoneEvent<'a> {
    job_id: JobId,
    id: &'a str,
    outcome: Outcome,
    error: Option<JvError>,
    version: Option<String>,
}

#[derive(Serialize, Clone)]
struct RunProgressEvent<'a> {
    job_id: JobId,
    id: &'a str,
    progress: f64,
}

#[derive(Serialize, Clone)]
struct RunDoneEvent<'a> {
    job_id: JobId,
    id: &'a str,
    outcome: Outcome,
    error: Option<JvError>,
    message: Option<String>,
    report: Option<serde_json::Value>,
}

#[tauri::command]
pub async fn jv_catalog<R: Runtime>(
    app: AppHandle<R>,
    fetch: bool,
) -> Result<CatalogView, JvError> {
    // Nettkallet går i en egen tråd, så det ikke holder igjen andre kommandoer.
    tauri::async_runtime::spawn_blocking(move || app.state::<Jv>().catalog(fetch))
        .await
        .map_err(|_| JvError::Internal)
}

#[tauri::command]
pub async fn jv_installed(state: State<'_, Jv>) -> Result<Vec<InstalledView>, JvError> {
    Ok(state.installed())
}

#[tauri::command]
pub async fn jv_install<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Jv>,
    id: String,
) -> Result<JobId, JvError> {
    // Feil som kan sies med en gang (ingen katalog, ikke for plattformen) går som svar.
    state.installable_entry(&id)?;
    let (job, cancel) = state.begin(&id)?;
    let app2 = app.clone();
    let id2 = id.clone();
    let spawned = std::thread::Builder::new()
        .name("jv-installasjon".into())
        .spawn(move || {
            let state = app2.state::<Jv>();
            let mut last: Option<Instant> = None;
            let result = catch_unwind(AssertUnwindSafe(|| {
                state.install(&id2, &cancel, &mut |phase, downloaded, total| {
                    if phase != InstallPhase::Download
                        || last.is_none_or(|t| t.elapsed() >= Duration::from_millis(200))
                        || downloaded == total
                    {
                        last = Some(Instant::now());
                        let _ = app2.emit(
                            EV_INSTALL_PROGRESS,
                            InstallProgressEvent {
                                job_id: job,
                                id: &id2,
                                phase,
                                downloaded,
                                total,
                            },
                        );
                    }
                })
            }))
            .unwrap_or(Err(JvError::Internal));
            state.end(job);
            let (outcome, error, version) = match result {
                Ok(v) => (Outcome::Completed, None, Some(v)),
                Err(JvError::Cancelled) => (Outcome::Cancelled, None, None),
                Err(e) => (Outcome::Failed, Some(e), None),
            };
            let _ = app2.emit(
                EV_INSTALL_DONE,
                InstallDoneEvent {
                    job_id: job,
                    id: &id2,
                    outcome,
                    error,
                    version,
                },
            );
        });
    if spawned.is_err() {
        state.end(job);
        return Err(JvError::Internal);
    }
    Ok(job)
}

#[tauri::command]
pub async fn jv_remove(state: State<'_, Jv>, id: String) -> Result<(), JvError> {
    state.remove(&id)
}

#[tauri::command]
pub async fn jv_run<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Jv>,
    id: String,
    request: RunRequest,
) -> Result<JobId, JvError> {
    let (job, cancel) = state.begin(&id)?;
    let cmd = match state.prepare_run(&id, &request) {
        Ok(c) => c,
        Err(e) => {
            state.end(job);
            return Err(e);
        }
    };
    let app2 = app.clone();
    let id2 = id.clone();
    let spawned = std::thread::Builder::new()
        .name("jv-kjoring".into())
        .spawn(move || {
            let state = app2.state::<Jv>();
            let result = catch_unwind(AssertUnwindSafe(|| {
                runner::run_job(cmd, &cancel, None, &mut |p| {
                    let _ = app2.emit(
                        EV_RUN_PROGRESS,
                        RunProgressEvent {
                            job_id: job,
                            id: &id2,
                            progress: p,
                        },
                    );
                })
            }))
            .unwrap_or(Err(JvError::Internal));
            state.end(job);
            let ev = |outcome, error, message, report| RunDoneEvent {
                job_id: job,
                id: &id2,
                outcome,
                error,
                message,
                report,
            };
            let done = match result {
                Ok(Finished::Report(r)) => ev(Outcome::Completed, None, None, Some(r)),
                Ok(Finished::Cancelled) => ev(Outcome::Cancelled, None, None, None),
                Ok(Finished::Failed { error, message }) => {
                    ev(Outcome::Failed, Some(error), message, None)
                }
                Err(e) => ev(Outcome::Failed, Some(e), None, None),
            };
            let _ = app2.emit(EV_RUN_DONE, done);
        });
    if spawned.is_err() {
        state.end(job);
        return Err(JvError::Internal);
    }
    Ok(job)
}

#[tauri::command]
pub async fn jv_cancel(state: State<'_, Jv>, job_id: JobId) -> Result<(), JvError> {
    state.cancel(job_id);
    Ok(())
}
