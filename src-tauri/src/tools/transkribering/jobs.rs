//! Jobbtabell: hvilke jobber som kjører, avbryt-flagg og «opptatt».
//!
//! whisper.cpp sjekker avbryt-flagget mellom hvert 30-sekundersvindu, ikke
//! midt i koderen. På en treg PC kan ett vindu ta over 10 sekunder (Windows-CI
//! med 2 vCPU: 13,9 s med small og beam 5). Derfor gjør `cancel` to ting for
//! transkribering:
//!
//! 1. Flagget settes, så whisper stopper ved neste sjekk.
//! 2. Jobben «slippes» med en gang: grensesnittet får `done` (avbrutt) straks,
//!    plassen frigjøres, og tråden sender ingen flere hendelser.
//!
//! En ny jobb kan da startes med en gang. Den venter på `run_lock` til den
//! gamle tråden er ferdig med vinduet sitt, så to whisper-jobber aldri kjører
//! samtidig.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use super::error::{CoreError, CoreResult};

pub type JobId = u64;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JobKind {
    Transcription,
    Download,
}

#[derive(Debug, Clone)]
pub struct JobHandle {
    pub id: JobId,
    pub kind: JobKind,
    pub cancel: Arc<AtomicBool>,
    /// Satt når grensesnittet allerede har fått `done`. Tråden sender da ingenting mer.
    pub abandoned: Arc<AtomicBool>,
    pub model_id: String,
}

impl JobHandle {
    pub fn is_abandoned(&self) -> bool {
        self.abandoned.load(Ordering::SeqCst)
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum CancelEffect {
    /// Ukjent eller allerede ferdig jobb.
    NotFound,
    /// Flagget er satt; jobben sender selv `done` når den stopper.
    Flagged,
    /// Transkribering sluppet: kalleren skal sende `done` (avbrutt) nå.
    Abandoned { model_id: String },
}

#[derive(Default)]
struct Inner {
    jobs: HashMap<JobId, JobHandle>,
    active_transcription: Option<JobId>,
    next: JobId,
}

#[derive(Default)]
pub struct JobTable {
    inner: Mutex<Inner>,
}

impl JobTable {
    fn lock(&self) -> std::sync::MutexGuard<'_, Inner> {
        self.inner.lock().unwrap_or_else(|e| e.into_inner())
    }

    fn insert(inner: &mut Inner, kind: JobKind, model_id: &str) -> JobHandle {
        inner.next += 1;
        let h = JobHandle {
            id: inner.next,
            kind,
            cancel: Arc::new(AtomicBool::new(false)),
            abandoned: Arc::new(AtomicBool::new(false)),
            model_id: model_id.to_string(),
        };
        inner.jobs.insert(h.id, h.clone());
        h
    }

    /// Ny transkribering, eller [`CoreError::Busy`] hvis en annen kjører.
    pub fn start_transcription(&self, model_id: &str) -> CoreResult<JobHandle> {
        let mut g = self.lock();
        if g.active_transcription.is_some() {
            return Err(CoreError::Busy);
        }
        let h = Self::insert(&mut g, JobKind::Transcription, model_id);
        g.active_transcription = Some(h.id);
        Ok(h)
    }

    pub fn start_download(&self, model_id: &str) -> JobHandle {
        let mut g = self.lock();
        Self::insert(&mut g, JobKind::Download, model_id)
    }

    pub fn cancel(&self, id: JobId) -> CancelEffect {
        let mut g = self.lock();
        let Some(h) = g.jobs.get(&id).cloned() else {
            return CancelEffect::NotFound;
        };
        h.cancel.store(true, Ordering::SeqCst);
        match h.kind {
            JobKind::Download => CancelEffect::Flagged,
            JobKind::Transcription => {
                if h.abandoned.swap(true, Ordering::SeqCst) {
                    return CancelEffect::NotFound;
                }
                g.jobs.remove(&id);
                if g.active_transcription == Some(id) {
                    g.active_transcription = None;
                }
                CancelEffect::Abandoned {
                    model_id: h.model_id,
                }
            }
        }
    }

    /// Kalles av tråden når jobben er ferdig. `true`: tråden skal sende `done`.
    pub fn finish(&self, h: &JobHandle) -> bool {
        let mut g = self.lock();
        g.jobs.remove(&h.id);
        if g.active_transcription == Some(h.id) {
            g.active_transcription = None;
        }
        !h.is_abandoned()
    }

    pub fn is_running(&self, id: JobId) -> bool {
        self.lock().jobs.contains_key(&id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_transcription_at_a_time() {
        let t = JobTable::default();
        let a = t.start_transcription("m").unwrap();
        assert_eq!(t.start_transcription("m").err(), Some(CoreError::Busy));
        // Nedlastinger kan gå samtidig.
        let d = t.start_download("m");
        assert_ne!(d.id, a.id);
        assert!(t.finish(&a));
        assert!(t.start_transcription("m").is_ok());
    }

    #[test]
    fn cancel_releases_transcription_at_once() {
        let t = JobTable::default();
        let a = t.start_transcription("modell-a").unwrap();
        assert_eq!(
            t.cancel(a.id),
            CancelEffect::Abandoned {
                model_id: "modell-a".into()
            }
        );
        assert!(a.cancel.load(Ordering::SeqCst));
        assert!(a.is_abandoned());
        // Plassen er ledig før den gamle tråden er ferdig.
        let b = t.start_transcription("modell-b").unwrap();
        // Den gamle tråden blir ferdig senere: sender ingen `done`, og rører ikke den nye.
        assert!(!t.finish(&a));
        assert_eq!(t.start_transcription("x").err(), Some(CoreError::Busy));
        assert!(t.is_running(b.id));
        // Dobbelt avbryt gir ingen ny `done`.
        assert_eq!(t.cancel(a.id), CancelEffect::NotFound);
        assert_eq!(t.cancel(9999), CancelEffect::NotFound);
    }

    #[test]
    fn download_cancel_only_sets_flag() {
        let t = JobTable::default();
        let d = t.start_download("m");
        assert_eq!(t.cancel(d.id), CancelEffect::Flagged);
        assert!(d.cancel.load(Ordering::SeqCst));
        assert!(!d.is_abandoned());
        assert!(t.is_running(d.id));
        assert!(t.finish(&d));
        assert!(!t.is_running(d.id));
    }
}
