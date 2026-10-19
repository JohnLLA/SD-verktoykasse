// SPDX-License-Identifier: AGPL-3.0-or-later
//! Planfilen fra `jv redact finn` (`<pdf>-treff.json`): lesing for visning og
//! lagring av avkrysningene.
//!
//! Webvisningen har ikke filtilgang, så dette går gjennom Rust. Det er smalt
//! med vilje:
//!
//! - Bare filer som heter `*-treff.json`, er `verktoy: "redact"` og er under
//!   [`MAX_PLAN_BYTES`] leses eller skrives.
//! - Lesing gir bare feltene visningen trenger (ikke rektanglene).
//! - Lagring endrer bare `sladd` på treff som finnes. Alt annet i filen,
//!   også `termer` og `kilde`, står urørt, så `jv redact sladd` godtar planen.
//! - Ingenting logges (regel 2).

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use serde::Serialize;
use serde_json::Value;

use super::error::{JvError, JvResult};

pub const MAX_PLAN_BYTES: u64 = 32 * 1024 * 1024;

fn invalid(reason: &'static str) -> JvError {
    JvError::InvalidArgs { reason }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PlanItem {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub page: Option<i64>,
    pub excerpt: String,
    pub placement: String,
    /// Skal sladdes (avkrysset).
    pub redact: bool,
    /// Mulig nummer der sifrene står langt fra hverandre (trolig tabellceller).
    pub rejected: bool,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PlanView {
    pub items: Vec<PlanItem>,
}

fn load(path: &str) -> JvResult<Value> {
    let p = Path::new(path);
    let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
    if !p.is_absolute() || !name.ends_with("-treff.json") {
        return Err(invalid("plan_path"));
    }
    let md = fs::symlink_metadata(p).map_err(|_| invalid("input_missing"))?;
    if !md.is_file() || md.len() > MAX_PLAN_BYTES {
        return Err(invalid("plan_path"));
    }
    let raw = fs::read(p)?;
    let v: Value = serde_json::from_slice(&raw).map_err(|_| invalid("plan_json"))?;
    if v.get("verktoy").and_then(Value::as_str) != Some("redact")
        || !v.get("treff").is_some_and(Value::is_array)
    {
        return Err(invalid("plan_json"));
    }
    Ok(v)
}

pub fn read_plan(path: &str) -> JvResult<PlanView> {
    let v = load(path)?;
    let items = v["treff"]
        .as_array()
        .map(|a| a.as_slice())
        .unwrap_or_default()
        .iter()
        .map(|t| {
            let s = |k: &str| t.get(k).and_then(Value::as_str).unwrap_or("").to_string();
            PlanItem {
                id: s("id"),
                kind: s("type"),
                page: t.get("side").and_then(Value::as_i64),
                excerpt: s("utdrag"),
                placement: s("plassering"),
                redact: t.get("sladd").and_then(Value::as_bool).unwrap_or(true),
                rejected: t.get("forkastet").and_then(Value::as_bool).unwrap_or(false),
                reason: t.get("grunn").and_then(Value::as_str).map(str::to_string),
            }
        })
        .collect();
    Ok(PlanView { items })
}

/// Setter `sladd` på treffene i `redact` (id → true/false). Ukjent id avvises.
pub fn save_plan(path: &str, redact: &BTreeMap<String, bool>) -> JvResult<()> {
    let mut v = load(path)?;
    let items = v["treff"].as_array_mut().ok_or(invalid("plan_json"))?;
    let mut seen = 0;
    for t in items.iter_mut() {
        let Some(id) = t.get("id").and_then(Value::as_str) else {
            continue;
        };
        if let Some(on) = redact.get(id) {
            t["sladd"] = Value::Bool(*on);
            seen += 1;
        }
    }
    if seen != redact.len() {
        return Err(invalid("plan_unknown_item"));
    }
    let mut out = serde_json::to_vec_pretty(&v).map_err(|_| JvError::Internal)?;
    out.push(b'\n');
    let tmp = Path::new(path).with_extension("json.tmp");
    let written = fs::write(&tmp, out).and_then(|_| fs::rename(&tmp, path));
    if let Err(e) = written {
        let _ = fs::remove_file(&tmp);
        return Err(e.into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn tmp(name: &str) -> String {
        let d = std::env::temp_dir().join(format!("jv-plan-{}-{}", std::process::id(), name));
        fs::create_dir_all(&d).unwrap();
        d.join("sak-treff.json").to_string_lossy().into_owned()
    }

    fn plan() -> Value {
        json!({
            "verktoy": "redact",
            "kilde": {"sha256": "x", "termer_sha256": "y"},
            "termer": ["Ola"],
            "treff": [
                {"id": "t1", "type": "fødselsnummer", "tekst": "01010112345", "side": 1,
                 "utdrag": "…", "plassering": "side", "rektangler": [[0, 0, 1, 1]], "sladd": true},
                {"id": "t2", "type": "telefon", "tekst": "58012345", "side": 2,
                 "utdrag": "…", "plassering": "side", "rektangler": [], "sladd": false,
                 "forkastet": true, "grunn": "tabell"}
            ]
        })
    }

    #[test]
    fn reads_only_what_the_screen_needs() {
        let p = tmp("read");
        fs::write(&p, plan().to_string()).unwrap();
        let view = read_plan(&p).unwrap();
        assert_eq!(view.items.len(), 2);
        assert!(view.items[0].redact && !view.items[0].rejected);
        assert!(!view.items[1].redact && view.items[1].rejected);
        assert_eq!(view.items[1].reason.as_deref(), Some("tabell"));
        let json = serde_json::to_string(&view).unwrap();
        assert!(!json.contains("01010112345"));
        assert!(!json.contains("rektangler"));
    }

    #[test]
    fn save_changes_only_the_redact_flag() {
        let p = tmp("save");
        fs::write(&p, plan().to_string()).unwrap();
        let mut m = BTreeMap::new();
        m.insert("t1".to_string(), false);
        m.insert("t2".to_string(), true);
        save_plan(&p, &m).unwrap();
        let after: Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
        let mut expected = plan();
        expected["treff"][0]["sladd"] = json!(false);
        expected["treff"][1]["sladd"] = json!(true);
        assert_eq!(after, expected);
    }

    #[test]
    fn rejects_other_files_and_unknown_items() {
        let p = tmp("bad");
        fs::write(&p, plan().to_string()).unwrap();
        let mut m = BTreeMap::new();
        m.insert("t9".to_string(), true);
        assert_eq!(save_plan(&p, &m).unwrap_err(), invalid("plan_unknown_item"));
        // Uendret etter avvist lagring.
        let after: Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
        assert_eq!(after, plan());

        let other = p.replace("-treff.json", ".json");
        fs::write(&other, plan().to_string()).unwrap();
        assert_eq!(read_plan(&other).unwrap_err(), invalid("plan_path"));
        assert_eq!(read_plan("relativ-treff.json").unwrap_err(), invalid("plan_path"));
        #[cfg(unix)]
        {
            let real = tmp("real");
            fs::write(&real, plan().to_string()).unwrap();
            let link = real.replace("sak-treff.json", "lenke-treff.json");
            let _ = fs::remove_file(&link);
            std::os::unix::fs::symlink(&real, &link).unwrap();
            assert_eq!(read_plan(&link).unwrap_err(), invalid("plan_path"));
        }
        let notplan = tmp("notplan");
        fs::write(&notplan, "{\"verktoy\":\"annet\",\"treff\":[]}").unwrap();
        assert_eq!(read_plan(&notplan).unwrap_err(), invalid("plan_json"));
    }
}
