// SPDX-License-Identifier: AGPL-3.0-or-later
//! Henting av katalogen (`tools.json` og `tools.json.sig`). Pakkene lastes ned
//! med nedlastingskoden fra Transkribering (`package::download_package`).
//!
//! Samme regler som modellnedlastingen: bare https og bare vertene i
//! [`HostPolicy`], omdirigeringer følges manuelt og hver ny vert sjekkes før vi
//! kobler til. Forespørselen har bare URL-en og en nøytral `User-Agent`;
//! ingenting om brukeren eller filene sendes.

use std::io::Read;
use std::time::Duration;

use crate::tools::transkribering::download::HostPolicy;
use crate::tools::transkribering::error::CoreError;

use super::error::{JvError, JvResult};

const MAX_REDIRECTS: usize = 8;

fn agent(allow_http: bool) -> ureq::Agent {
    use ureq::tls::{RootCerts, TlsConfig};
    let tls = TlsConfig::builder()
        .root_certs(RootCerts::PlatformVerifier)
        .build();
    let cfg = ureq::Agent::config_builder()
        .max_redirects(0)
        .http_status_as_error(false)
        .https_only(!allow_http)
        .tls_config(tls)
        .user_agent("lla-verktoykasse")
        .timeout_global(Some(Duration::from_secs(60)))
        .build();
    ureq::Agent::new_with_config(cfg)
}

fn resolve_location(current: &str, location: &str) -> Option<String> {
    if location.starts_with("https://") || location.starts_with("http://") {
        return Some(location.to_string());
    }
    if location.starts_with('/') && !location.starts_with("//") {
        let uri: ureq::http::Uri = current.parse().ok()?;
        let scheme = uri.scheme_str()?;
        let auth = uri.authority()?.as_str();
        return Some(format!("{scheme}://{auth}{location}"));
    }
    None
}

/// Henter en liten fil (høyst `max_bytes`). Feil blir `JvError::Download`.
pub fn fetch_small(policy: &HostPolicy, url: &str, max_bytes: usize) -> JvResult<Vec<u8>> {
    let allow_http = url.starts_with("http://");
    let agent = agent(allow_http);
    let mut url = url.to_string();
    for _ in 0..=MAX_REDIRECTS {
        policy.check(&url).map_err(JvError::from)?;
        let resp = agent.get(&url).call().map_err(|_| JvError::Download {
            cause: CoreError::Network,
        })?;
        let status = resp.status().as_u16();
        match status {
            301 | 302 | 303 | 307 | 308 => {
                url = resp
                    .headers()
                    .get("location")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|l| resolve_location(&url, l))
                    .ok_or(JvError::Download {
                        cause: CoreError::HttpStatus { status },
                    })?;
            }
            200 => {
                let mut data = Vec::new();
                resp.into_body()
                    .into_reader()
                    .take(max_bytes as u64 + 1)
                    .read_to_end(&mut data)
                    .map_err(|_| JvError::Download {
                        cause: CoreError::Network,
                    })?;
                if data.len() > max_bytes {
                    return Err(JvError::CatalogInvalid {
                        reason: "too_large",
                    });
                }
                return Ok(data);
            }
            _ => {
                return Err(JvError::Download {
                    cause: CoreError::HttpStatus { status },
                })
            }
        }
    }
    Err(JvError::Download {
        cause: CoreError::HttpStatus { status: 310 },
    })
}
