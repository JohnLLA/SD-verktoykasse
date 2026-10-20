//! Oppdatering av appen (spesifikasjonen: «Nettverk og personvern», kall 2).
//!
//! Alt nettarbeid skjer her i Rust, aldri i webvisningen. Webvisningen får
//! ingen `updater:*`-tillatelser og kan bare be om to ting: «finnes det en ny
//! versjon?» og «installer den». Det eneste som sendes, er en forespørsel om
//! `latest.json` fra adressen i `tauri.conf.json` (`plugins.updater.endpoints`).
//! Ingen lyd, tekst, filnavn eller brukerdata er med.
//!
//! Kontrollene er doble:
//! - Er bryteren «Se etter ny versjon når appen starter» slått av (eller kan
//!   ikke leses), gjør den automatiske sjekken ingenting og ringer ikke ut, også
//!   om grensesnittet skulle be om det. Bare knappen «Se etter ny versjon nå»
//!   (`manual`) sjekker uansett, fordi brukeren ber om det selv.
//! - Nedlastingsadressen i `latest.json` må peke på releases-repoet på GitHub,
//!   ellers nektes installasjonen. I tillegg verifiseres hver pakke mot den
//!   offentlige nøkkelen i konfigurasjonen før den installeres.
//!
//! Ingenting her skriver adresser, tjenersvar eller feilmeldinger til logg
//! (regel 2).

use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Manager, Runtime, State, Url};
use tauri_plugin_store::StoreExt;
use tauri_plugin_updater::{Update, UpdaterExt};

/// Må stemme med `KEYS.versionCheck` i `src/lib/settings.ts` (testet).
pub const VERSION_CHECK_KEY: &str = "shell.versionCheck";
const SETTINGS_FILE: &str = "settings.json";

/// Eneste sted en oppdateringspakke kan lastes ned fra (sti med små bokstaver).
const ALLOWED_DOWNLOAD_HOST: &str = "github.com";
const ALLOWED_DOWNLOAD_PATH_PREFIX: &str = "/johnlla/lla-verktoykasse-releases/releases/download/";

/// Funnet, men ikke installert oppdatering.
#[derive(Default)]
pub struct PendingUpdate(Mutex<Option<Update>>);

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct UpdateInfo {
    pub version: String,
}

/// Feilkoder frontend viser tekst for. Aldri detaljer fra nettet.
#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum UpdateError {
    /// Bryteren er av.
    Disabled,
    /// Ingen funnet oppdatering å installere.
    NothingPending,
    /// Adressen i oppdateringsfilen er ikke den vi tillater.
    Blocked,
    /// Sjekken eller installasjonen feilet (ingen nett, ugyldig signatur ...).
    Failed,
}

/// Skal oppstartssjekken gjøres? Sikker standard: kan innstillingen ikke
/// leses, eller har den en uventet verdi, sjekkes det ikke automatisk.
/// Er den aldri lagret (første oppstart), gjelder standarden «på».
pub fn auto_check_allowed(stored: Result<Option<serde_json::Value>, ()>) -> bool {
    match stored {
        Ok(None) => true,
        Ok(Some(v)) => v.as_bool().unwrap_or(false),
        Err(()) => false,
    }
}

fn read_version_check<R: Runtime>(app: &AppHandle<R>) -> Result<Option<serde_json::Value>, ()> {
    let store = app.store(SETTINGS_FILE).map_err(|_| ())?;
    Ok(store.get(VERSION_CHECK_KEY))
}

/// Er dette en nedlastingsadresse vi stoler på?
pub fn is_allowed_download_url(url: &Url) -> bool {
    url.scheme() == "https"
        && url.host_str().is_some_and(|h| h.eq_ignore_ascii_case(ALLOWED_DOWNLOAD_HOST))
        && url.port().is_none()
        && url.username().is_empty()
        && url.password().is_none()
        && url.path().to_ascii_lowercase().starts_with(ALLOWED_DOWNLOAD_PATH_PREFIX)
}

/// Sjekker om det finnes en nyere versjon. `Ok(None)` = ingen ny.
///
/// `manual` er `true` bare når brukeren selv trykker «Se etter ny versjon nå».
/// Da sjekkes det uansett bryteren. Ellers (oppstart) kreves det at bryteren er på.
#[tauri::command]
pub async fn check_for_update<R: Runtime>(
    app: AppHandle<R>,
    pending: State<'_, PendingUpdate>,
    manual: Option<bool>,
) -> Result<Option<UpdateInfo>, UpdateError> {
    if !manual.unwrap_or(false) && !auto_check_allowed(read_version_check(&app)) {
        return Err(UpdateError::Disabled);
    }
    let updater = app.updater().map_err(|_| UpdateError::Failed)?;
    let found = updater.check().await.map_err(|_| UpdateError::Failed)?;
    let info = found.as_ref().map(|u| UpdateInfo { version: u.version.clone() });
    *pending.0.lock().map_err(|_| UpdateError::Failed)? = found;
    Ok(info)
}

/// Laster ned, verifiserer signaturen og installerer oppdateringen som
/// `check_for_update` fant, og starter appen på nytt. Brukeren har trykket
/// «Oppdater nå» før dette kalles.
#[tauri::command]
pub async fn install_update<R: Runtime>(
    app: AppHandle<R>,
    pending: State<'_, PendingUpdate>,
) -> Result<(), UpdateError> {
    let update = pending
        .0
        .lock()
        .map_err(|_| UpdateError::Failed)?
        .clone()
        .ok_or(UpdateError::NothingPending)?;
    if !is_allowed_download_url(&update.download_url) {
        return Err(UpdateError::Blocked);
    }
    update
        .download_and_install(|_, _| {}, || {})
        .await
        .map_err(|_| UpdateError::Failed)?;
    // Windows: installasjonsprogrammet avslutter appen selv. Mac: start på nytt her.
    app.restart();
}

pub fn manage<R: Runtime>(app: &AppHandle<R>) {
    app.manage(PendingUpdate::default());
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok(u: &str) -> bool {
        is_allowed_download_url(&Url::parse(u).unwrap())
    }

    #[test]
    fn allows_only_our_release_downloads() {
        assert!(ok("https://github.com/JohnLLA/lla-verktoykasse-releases/releases/download/v0.2.0/SD-Verktoy_0.2.0_x64.msi"));
        assert!(!ok("https://github.com/JohnLLA/lla-verktoykasse/releases/download/v0.2.0/x.msi"));
        assert!(!ok("https://github.com/Annen/lla-verktoykasse-releases/releases/download/v1/x.msi"));
        assert!(!ok("http://github.com/JohnLLA/lla-verktoykasse-releases/releases/download/v1/x.msi"));
        assert!(!ok("https://evil.example/JohnLLA/lla-verktoykasse-releases/releases/download/v1/x.msi"));
        assert!(!ok("https://github.com.evil.example/JohnLLA/lla-verktoykasse-releases/releases/download/v1/x"));
        assert!(!ok("https://github.com@evil.example/JohnLLA/lla-verktoykasse-releases/releases/download/v1/x"));
        assert!(!ok("https://github.com:8443/JohnLLA/lla-verktoykasse-releases/releases/download/v1/x"));
    }

    #[test]
    fn automatic_check_has_safe_default() {
        use serde_json::json;
        assert!(auto_check_allowed(Ok(None))); // aldri satt: standard er på
        assert!(auto_check_allowed(Ok(Some(json!(true)))));
        assert!(!auto_check_allowed(Ok(Some(json!(false)))));
        assert!(!auto_check_allowed(Ok(Some(json!("true"))))); // uventet verdi
        assert!(!auto_check_allowed(Ok(Some(json!(null)))));
        assert!(!auto_check_allowed(Err(()))); // kan ikke leses
    }

    #[test]
    fn version_check_key_matches_frontend() {
        let ts = include_str!("../../src/lib/settings.ts");
        assert!(ts.contains(&format!("versionCheck: \"{VERSION_CHECK_KEY}\"")));
    }
}
