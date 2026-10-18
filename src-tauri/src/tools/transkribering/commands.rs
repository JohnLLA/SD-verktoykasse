//! Tauri-kommandoene og -hendelsene for Transkribering.
//!
//! Kommandoer (kalles som `plugin:transkribering|<navn>`):
//!
//! | Kommando | Inn | Ut |
//! |---|---|---|
//! | `check_system` | – | [`SystemInfo`] |
//! | `list_models` | – | [`ModelList`] |
//! | `download_model` | `model_id` | jobb-ID; hendelser `download-progress`/`download-done` |
//! | `delete_model` | `model_id` | – |
//! | `set_model_dir` | `path` (eller `null` for å fjerne) | – |
//! | `transcribe` | [`TranscribeRequest`] | jobb-ID; hendelser `progress`/`segment`/`done` |
//! | `cancel` | `job_id` | – (transkribering: `done` sendes med en gang; nedlasting) |
//! | `suggest_export_path` | lydfil, målform, stil, format | sti |
//! | `export` | [`ExportRequest`] | stien som ble skrevet |
//!
//! Hendelser (`transkribering:<navn>`), alle med `job_id`:
//! `progress {percent, eta_ms}`, `segment {start_ms, end_ms, text}`,
//! `done {outcome, error, model_id, duration_ms, segments}`,
//! `download-progress {model_id, downloaded, total}`,
//! `download-done {model_id, outcome, error}`.
//!
//! Feil er [`CoreError`] (`{"code": ...}`). Grensesnittet lager teksten.
//! Ingenting her logger; transkribert tekst går bare til grensesnittet.

use std::collections::HashSet;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, Runtime, State};
use tauri_plugin_store::StoreExt;

use super::download::{download_model as run_download, HostPolicy};
use super::engine::{run_job, EngineEvent, JobRequest};
use super::error::{CoreError, CoreResult};
use super::export::{
    default_export_path, render, write_file, ExportFormat, ExportMeta, HeaderLabels,
};
use super::jobs::{CancelEffect, JobTable};
use super::models::{self, Catalog, Choice, ModelDirs, ModelStatus, VerifyCache};
use super::system::{self, SystemInfo};
use super::types::{Decoding, Kvalitet, Malform, Segment, Stil};

/// Innstillingsfilen (Tauri store-plugin), delt med grensesnittet.
pub const SETTINGS_FILE: &str = "settings.json";
/// Nøkkel for egen modellmappe (streng, eller fraværende).
pub const MODEL_DIR_KEY: &str = "transkribering.modelDir";

pub const EV_PROGRESS: &str = "transkribering:progress";
pub const EV_SEGMENT: &str = "transkribering:segment";
pub const EV_DONE: &str = "transkribering:done";
pub const EV_DOWNLOAD_PROGRESS: &str = "transkribering:download-progress";
pub const EV_DOWNLOAD_DONE: &str = "transkribering:download-done";

pub use super::jobs::JobId;

/// Tilstanden til verktøyet, lagt i Tauri med `manage`.
pub struct Transkribering {
    catalog: Catalog,
    policy: HostPolicy,
    app_model_dir: PathBuf,
    verify_cache_path: PathBuf,
    verify_cache: Mutex<VerifyCache>,
    jobs: JobTable,
    /// Modeller som lastes ned nå (samme modell to ganger ville skrevet til samme `.part`).
    downloads: Mutex<HashSet<String>>,
    /// Holdes mens whisper kjører, så en ny jobb venter til en avbrutt er helt ute.
    run_lock: Mutex<()>,
}

impl Transkribering {
    pub fn new(app_data_dir: PathBuf) -> CoreResult<Self> {
        let catalog = Catalog::builtin()?;
        let policy = HostPolicy::production(&catalog);
        let verify_cache_path = app_data_dir.join("modeller-sjekket.json");
        Ok(Transkribering {
            verify_cache: Mutex::new(VerifyCache::load(&verify_cache_path)),
            verify_cache_path,
            app_model_dir: app_data_dir.join("modeller"),
            catalog,
            policy,
            jobs: JobTable::default(),
            downloads: Mutex::new(HashSet::new()),
            run_lock: Mutex::new(()),
        })
    }

    fn dirs<R: Runtime>(&self, app: &AppHandle<R>) -> ModelDirs {
        ModelDirs {
            app_dir: self.app_model_dir.clone(),
            custom_dir: custom_model_dir(app),
        }
    }
}

fn custom_model_dir<R: Runtime>(app: &AppHandle<R>) -> Option<PathBuf> {
    let store = app.store(SETTINGS_FILE).ok()?;
    let v = store.get(MODEL_DIR_KEY)?;
    let s = v.as_str()?.trim().to_string();
    (!s.is_empty()).then(|| PathBuf::from(s))
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Completed,
    Cancelled,
    Failed,
}

fn outcome_of<T>(r: &CoreResult<T>) -> (Outcome, Option<CoreError>) {
    match r {
        Ok(_) => (Outcome::Completed, None),
        Err(CoreError::Cancelled) => (Outcome::Cancelled, None),
        Err(e) => (Outcome::Failed, Some(e.clone())),
    }
}

// ---------- check_system ----------

#[tauri::command]
pub async fn check_system() -> SystemInfo {
    system::info()
}

// ---------- list_models ----------

#[derive(Debug, Clone, Serialize)]
pub struct ModelList {
    pub models: Vec<ModelStatus>,
    /// Hvilken modell hver kombinasjon av stil og kvalitet bruker.
    pub choices: Vec<Choice>,
    /// Appens modellmappe (nedlastinger havner her).
    pub app_model_dir: String,
    /// Brukerens egen modellmappe, hvis satt.
    pub custom_model_dir: Option<String>,
    pub license: String,
    pub license_holder: String,
}

#[tauri::command]
pub async fn list_models<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Transkribering>,
) -> Result<ModelList, CoreError> {
    let dirs = state.dirs(&app);
    Ok(ModelList {
        models: state
            .catalog
            .models
            .iter()
            .map(|m| models::status(m, &dirs))
            .collect(),
        choices: state.catalog.choices(),
        app_model_dir: dirs.app_dir.to_string_lossy().to_string(),
        custom_model_dir: dirs.custom_dir.map(|d| d.to_string_lossy().to_string()),
        license: state.catalog.license.clone(),
        license_holder: state.catalog.license_holder.clone(),
    })
}

// ---------- download_model ----------

#[derive(Debug, Clone, Serialize)]
struct DownloadProgressEvent<'a> {
    job_id: JobId,
    model_id: &'a str,
    downloaded: u64,
    total: u64,
}

#[derive(Debug, Clone, Serialize)]
struct DownloadDoneEvent<'a> {
    job_id: JobId,
    model_id: &'a str,
    outcome: Outcome,
    error: Option<CoreError>,
}

#[tauri::command]
pub async fn download_model<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Transkribering>,
    model_id: String,
) -> Result<JobId, CoreError> {
    let entry = state
        .catalog
        .get(&model_id)
        .cloned()
        .ok_or(CoreError::UnknownModel)?;
    {
        let mut d = state.downloads.lock().map_err(|_| CoreError::Internal)?;
        if !d.insert(model_id.clone()) {
            return Err(CoreError::AlreadyDownloading);
        }
    }
    let dirs = state.dirs(&app);
    let job = state.jobs.start_download(&model_id);
    let job_id = job.id;
    let job_on_error = job.clone();
    let app2 = app.clone();
    let spawned = std::thread::Builder::new()
        .name("modellnedlasting".into())
        .spawn(move || {
            let state = app2.state::<Transkribering>();
            let mut last: Option<Instant> = None;
            let result = catch_unwind(AssertUnwindSafe(|| {
                run_download(
                    &entry,
                    &dirs,
                    &state.policy,
                    &job.cancel,
                    &mut |downloaded, total| {
                        if last.is_none_or(|t| t.elapsed() >= Duration::from_millis(200))
                            || downloaded == total
                        {
                            last = Some(Instant::now());
                            let _ = app2.emit(
                                EV_DOWNLOAD_PROGRESS,
                                DownloadProgressEvent {
                                    job_id,
                                    model_id: &entry.id,
                                    downloaded,
                                    total,
                                },
                            );
                        }
                    },
                )
            }))
            .unwrap_or(Err(CoreError::Internal));
            let (outcome, error) = outcome_of(&result);
            if let Ok(mut d) = state.downloads.lock() {
                d.remove(&entry.id);
            }
            state.jobs.finish(&job);
            let _ = app2.emit(
                EV_DOWNLOAD_DONE,
                DownloadDoneEvent {
                    job_id,
                    model_id: &entry.id,
                    outcome,
                    error,
                },
            );
        });
    if spawned.is_err() {
        if let Ok(mut d) = state.downloads.lock() {
            d.remove(&model_id);
        }
        state.jobs.finish(&job_on_error);
        return Err(CoreError::Internal);
    }
    Ok(job_id)
}

// ---------- delete_model ----------

#[tauri::command]
pub async fn delete_model<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Transkribering>,
    model_id: String,
) -> Result<(), CoreError> {
    let entry = state
        .catalog
        .get(&model_id)
        .ok_or(CoreError::UnknownModel)?;
    if state
        .downloads
        .lock()
        .map(|d| d.contains(&model_id))
        .unwrap_or(false)
    {
        return Err(CoreError::AlreadyDownloading);
    }
    models::delete(entry, &state.dirs(&app))
}

// ---------- set_model_dir ----------

#[tauri::command]
pub async fn set_model_dir<R: Runtime>(
    app: AppHandle<R>,
    path: Option<String>,
) -> Result<(), CoreError> {
    let store = app.store(SETTINGS_FILE).map_err(|_| CoreError::Internal)?;
    match path.map(|p| p.trim().to_string()).filter(|p| !p.is_empty()) {
        Some(p) => {
            if !Path::new(&p).is_dir() {
                return Err(CoreError::NotADirectory);
            }
            store.set(MODEL_DIR_KEY, serde_json::Value::String(p));
        }
        None => {
            store.delete(MODEL_DIR_KEY);
        }
    }
    store.save().map_err(|_| CoreError::Io {
        kind: "store".into(),
    })
}

// ---------- transcribe ----------

#[derive(Debug, Clone, Deserialize)]
pub struct TranscribeRequest {
    pub audio_path: String,
    pub malform: Malform,
    pub stil: Stil,
    pub kvalitet: Kvalitet,
    /// Standard: beam 5.
    #[serde(default)]
    pub decoding: Decoding,
}

#[derive(Debug, Clone, Serialize)]
struct ProgressEvent {
    job_id: JobId,
    percent: f64,
    eta_ms: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
struct SegmentEvent<'a> {
    job_id: JobId,
    start_ms: u64,
    end_ms: u64,
    text: &'a str,
}

#[derive(Debug, Clone, Serialize)]
struct DoneEvent {
    job_id: JobId,
    outcome: Outcome,
    error: Option<CoreError>,
    model_id: String,
    duration_ms: u64,
    segments: Vec<Segment>,
}

#[tauri::command]
pub async fn transcribe<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Transkribering>,
    request: TranscribeRequest,
) -> Result<JobId, CoreError> {
    let missing = system::missing_cpu_features();
    if !missing.is_empty() {
        return Err(CoreError::CpuUnsupported { missing });
    }
    let entry = state
        .catalog
        .select(request.stil, request.kvalitet)?
        .clone();
    let options = state.catalog.options_for(&entry);
    let dirs = state.dirs(&app);
    let (model_path, location) = dirs.locate(&entry).ok_or(CoreError::ModelMissing {
        model_id: entry.id.clone(),
    })?;
    let audio = PathBuf::from(&request.audio_path);
    if !audio.is_file() {
        return Err(CoreError::FileNotFound);
    }
    let handle = state.jobs.start_transcription(&entry.id)?;
    let job_id = handle.id;
    let mut job = JobRequest::new(audio, model_path.clone(), request.malform, options);
    job.decoding = request.decoding;
    let app2 = app.clone();
    let handle2 = handle.clone();
    let spawned = std::thread::Builder::new()
        .name("transkribering".into())
        .spawn(move || {
            let state = app2.state::<Transkribering>();
            let cancel = &handle.cancel;
            // Venter til en avbrutt jobb er helt ferdig (whisper sjekker bare
            // avbryt mellom vinduene), så to jobber aldri kjører samtidig.
            let _run = state.run_lock.lock().unwrap_or_else(|e| e.into_inner());
            let mut duration_ms = 0;
            let result = catch_unwind(AssertUnwindSafe(|| -> CoreResult<Vec<Segment>> {
                // Modeller i egen mappe sjekkes mot SHA-256 første gang.
                {
                    let mut cache = state.verify_cache.lock().map_err(|_| CoreError::Internal)?;
                    if models::ensure_verified(&model_path, location, &entry, &mut cache, cancel)? {
                        let _ = cache.save(&state.verify_cache_path);
                    }
                }
                let r = run_job(&job, cancel, &mut |ev| {
                    if handle.is_abandoned() {
                        return;
                    }
                    match ev {
                        EngineEvent::Progress { percent, eta_ms } => {
                            let _ = app2.emit(
                                EV_PROGRESS,
                                ProgressEvent {
                                    job_id,
                                    percent,
                                    eta_ms,
                                },
                            );
                        }
                        EngineEvent::Segment(s) => {
                            let _ = app2.emit(
                                EV_SEGMENT,
                                SegmentEvent {
                                    job_id,
                                    start_ms: s.start_ms,
                                    end_ms: s.end_ms,
                                    text: &s.text,
                                },
                            );
                        }
                    }
                })?;
                duration_ms = r.duration_ms;
                Ok(r.segments)
            }))
            .unwrap_or(Err(CoreError::Internal));
            let (outcome, error) = outcome_of(&result);
            if state.jobs.finish(&handle) {
                let _ = app2.emit(
                    EV_DONE,
                    DoneEvent {
                        job_id,
                        outcome,
                        error,
                        model_id: entry.id.clone(),
                        duration_ms,
                        segments: result.unwrap_or_default(),
                    },
                );
            }
        });
    if spawned.is_err() {
        state.jobs.finish(&handle2);
        return Err(CoreError::Internal);
    }
    Ok(job_id)
}

// ---------- cancel ----------

/// Avbryter en transkribering eller nedlasting. En transkribering slippes med
/// en gang: `done` (avbrutt) sendes nå, og en ny jobb kan startes, selv om
/// whisper bruker noen sekunder på å bli ferdig med vinduet sitt (jobs.rs).
#[tauri::command]
pub async fn cancel<R: Runtime>(
    app: AppHandle<R>,
    state: State<'_, Transkribering>,
    job_id: JobId,
) -> Result<(), CoreError> {
    if let CancelEffect::Abandoned { model_id } = state.jobs.cancel(job_id) {
        let _ = app.emit(
            EV_DONE,
            DoneEvent {
                job_id,
                outcome: Outcome::Cancelled,
                error: None,
                model_id,
                duration_ms: 0,
                segments: Vec::new(),
            },
        );
    }
    Ok(())
}

// ---------- eksport ----------

#[tauri::command]
pub async fn suggest_export_path(
    audio_path: String,
    malform: Malform,
    stil: Stil,
    format: ExportFormat,
) -> String {
    default_export_path(Path::new(&audio_path), malform, stil, format)
        .to_string_lossy()
        .to_string()
}

#[derive(Debug, Clone, Deserialize)]
pub struct ExportRequest {
    /// Lydfilen; brukes for filnavnet i toppteksten og standard lagringssted.
    pub audio_path: String,
    /// Hvor filen skal lagres. `None`: standard (`<lydfil>.<målform>.<stil>.<ending>`).
    #[serde(default)]
    pub target_path: Option<String>,
    pub format: ExportFormat,
    /// Tidskoder i txt og docx.
    #[serde(default)]
    pub timestamps: bool,
    /// Bare `true` etter at brukeren har bekreftet overskriving.
    #[serde(default)]
    pub overwrite: bool,
    /// Segmentene slik de står i grensesnittet (med brukerens rettelser).
    pub segments: Vec<Segment>,
    pub malform: Malform,
    pub stil: Stil,
    pub model_id: String,
    /// Datoen som vises i toppteksten, laget av grensesnittet (lokal tid).
    pub date: String,
    pub labels: HeaderLabels,
}

#[tauri::command]
pub async fn export(
    state: State<'_, Transkribering>,
    request: ExportRequest,
) -> Result<String, CoreError> {
    let entry = state
        .catalog
        .get(&request.model_id)
        .ok_or(CoreError::UnknownModel)?;
    let audio = Path::new(&request.audio_path);
    let target = match &request.target_path {
        Some(p) if !p.trim().is_empty() => PathBuf::from(p),
        _ => default_export_path(audio, request.malform, request.stil, request.format),
    };
    let meta = ExportMeta {
        audio_file_name: audio
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default(),
        date: request.date.clone(),
        malform: request.malform,
        stil: request.stil,
        model: format!("{} ({})", entry.repo, entry.quant),
        labels: request.labels.clone(),
    };
    let bytes = render(request.format, &request.segments, &meta, request.timestamps)?;
    write_file(&target, &bytes, request.overwrite)?;
    Ok(target.to_string_lossy().to_string())
}
