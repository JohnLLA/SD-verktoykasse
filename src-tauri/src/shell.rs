//! Skallets egne Tauri-kommandoer. Ikke en del av noe verktøy.
//!
//! Avspilling av lokal lyd går gjennom Tauris asset-protokoll (`asset:`), ikke
//! nett. Protokollen er slått på uten noen faste tillatte stier
//! (`tauri.conf.json`: `assetProtocol.scope` er tom). Grensesnittet ber om
//! tilgang til én fil om gangen, og bare for lyd- og videofiler brukeren selv
//! har valgt eller sluppet i vinduet.

use std::path::Path;

use tauri::{AppHandle, Manager, Runtime};

/// Filendelser vi åpner for avspilling. Samme liste som verktøyet leser
/// (spesifikasjonen, «Filer inn»).
const PLAYABLE: &[&str] = &["mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "mp4", "mov"];

fn is_playable(path: &Path) -> bool {
    path.is_file()
        && path
            .extension()
            .map(|e| e.to_string_lossy().to_lowercase())
            .is_some_and(|e| PLAYABLE.contains(&e.as_str()))
}

/// Gir `asset:`-protokollen lov til å lese akkurat denne filen. Returnerer
/// `false` hvis filen ikke finnes eller ikke er lyd/video. Ingenting logges.
#[tauri::command]
pub fn allow_playback<R: Runtime>(app: AppHandle<R>, path: String) -> bool {
    let p = Path::new(&path);
    is_playable(p) && app.asset_protocol_scope().allow_file(p).is_ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("lla-shell-{}-{name}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn only_existing_audio_and_video_files_are_playable() {
        let d = tmp("avspilling");
        let mp3 = d.join("Intervju æøå.MP3");
        let txt = d.join("notat.txt");
        std::fs::write(&mp3, b"x").unwrap();
        std::fs::write(&txt, b"x").unwrap();
        assert!(is_playable(&mp3));
        assert!(!is_playable(&txt));
        assert!(!is_playable(&d.join("finnes-ikke.mp3")));
        // En mappe med lydendelse er ikke en fil.
        let dir = d.join("mappe.wav");
        std::fs::create_dir_all(&dir).unwrap();
        assert!(!is_playable(&dir));
        let _ = std::fs::remove_dir_all(&d);
    }
}
