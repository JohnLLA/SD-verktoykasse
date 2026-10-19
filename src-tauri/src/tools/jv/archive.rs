// SPDX-License-Identifier: AGPL-3.0-or-later
//! Trygg utpakking av verktøypakker (`.tar.gz` på Mac, `.zip` på Windows).
//!
//! Systemets `tar` (bsdtar/libarchive: `/usr/bin/tar` på macOS,
//! `%SystemRoot%\System32\tar.exe` på Windows 10 1803+) leser arkivet og
//! skriver det ut igjen som en ukomprimert tar-strøm (`tar -c -f - @arkiv`).
//! Den skriver aldri noe til disken. Strømmen leses her, og alt som havner på
//! disken, skrives av denne koden etter kontroll:
//!
//! - Bare vanlige filer, mapper og symlenker. Harde lenker, enheter og FIFO-er avvises.
//! - Stier må være relative, uten `..`, uten `\` og `:` og uten tomme deler.
//! - En symlenke må peke innenfor mappen (relativt), og ingen sti får gå
//!   gjennom en symlenke. På Windows avvises symlenker helt.
//! - Ingen sti kan komme to ganger, og ingenting overskrives (`create_new`).
//! - setuid/setgid/sticky fjernes; bare kjørbarhet beholdes.
//! - Tak på antall oppføringer og total størrelse (mot «zip-bomber»).
//!
//! Hvorfor ikke `tar`/`flate2`/`zip`-cratene: de er ikke godkjent som direkte
//! avhengigheter (regel 7). De ligger allerede i Cargo.lock via
//! tauri-plugin-updater; å ta dem i bruk direkte er en beslutning for John Inge
//! (docs/spike-sidecar.md).

use std::collections::HashSet;
use std::fs::{self, OpenOptions};
use std::io::{BufReader, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};

use super::error::{JvError, JvResult};

pub const MAX_ENTRIES: usize = 200_000;
pub const MAX_TOTAL_BYTES: u64 = 4 * 1024 * 1024 * 1024;

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct ExtractStats {
    pub files: usize,
    pub dirs: usize,
    pub symlinks: usize,
    pub bytes: u64,
}

fn system_tar() -> PathBuf {
    #[cfg(windows)]
    {
        let root = std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into());
        PathBuf::from(root).join("System32").join("tar.exe")
    }
    #[cfg(not(windows))]
    {
        PathBuf::from("/usr/bin/tar")
    }
}

/// Pakker ut `archive` til `dest`, som må finnes og være tom.
pub fn extract(archive: &Path, dest: &Path) -> JvResult<ExtractStats> {
    if fs::read_dir(dest)?.next().is_some() {
        return Err(JvError::UnsafeArchive {
            reason: "dest_not_empty",
        });
    }
    let mut arg = std::ffi::OsString::from("@");
    arg.push(archive.as_os_str());
    let mut child = Command::new(system_tar())
        .args(["-c", "-f", "-", "--format", "pax"])
        .arg(arg)
        .env_clear()
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| JvError::ArchiveRead)?;
    let stdout = child.stdout.take().ok_or(JvError::ArchiveRead)?;
    let result = extract_tar_stream(BufReader::with_capacity(1 << 20, stdout), dest);
    if result.is_err() {
        let _ = child.kill();
    }
    let status = child.wait().map_err(|_| JvError::ArchiveRead)?;
    let stats = result?;
    if !status.success() {
        return Err(JvError::ArchiveRead);
    }
    Ok(stats)
}

/// En kontrollert, relativ sti delt i deler.
fn checked_parts(raw: &str) -> JvResult<Vec<String>> {
    let unsafe_path = |reason| Err(JvError::UnsafeArchive { reason });
    if raw.is_empty() || raw.starts_with('/') {
        return unsafe_path("absolute");
    }
    if raw.contains('\\') || raw.contains(':') || raw.contains('\0') {
        return unsafe_path("bad_char");
    }
    let mut parts = Vec::new();
    for p in raw.split('/') {
        match p {
            "" | "." => continue,
            ".." => return unsafe_path("dotdot"),
            _ => parts.push(p.to_string()),
        }
    }
    if parts.is_empty() {
        return unsafe_path("empty");
    }
    Ok(parts)
}

/// Peker symlenken `link_parts` → `target` innenfor roten?
fn symlink_stays_inside(link_parts: &[String], target: &str) -> bool {
    if target.is_empty() || target.starts_with('/') || target.contains('\\') || target.contains(':')
    {
        return false;
    }
    // Mappen lenken ligger i.
    let mut depth: Vec<&str> = link_parts[..link_parts.len() - 1]
        .iter()
        .map(|s| s.as_str())
        .collect();
    for p in target.split('/') {
        match p {
            "" | "." => {}
            ".." => {
                if depth.pop().is_none() {
                    return false;
                }
            }
            other => depth.push(other),
        }
    }
    true
}

fn octal(field: &[u8]) -> JvResult<u64> {
    // GNU base-256 for store tall.
    if let Some(&first) = field.first() {
        if first & 0x80 != 0 {
            let mut v: u64 = (first & 0x7f) as u64;
            for &b in &field[1..] {
                v = v.checked_mul(256).ok_or(JvError::ArchiveRead)? + b as u64;
            }
            return Ok(v);
        }
    }
    let s: String = field
        .iter()
        .take_while(|&&b| b != 0)
        .map(|&b| b as char)
        .collect();
    let s = s.trim();
    if s.is_empty() {
        return Ok(0);
    }
    u64::from_str_radix(s, 8).map_err(|_| JvError::ArchiveRead)
}

fn cstr(field: &[u8]) -> JvResult<String> {
    let end = field.iter().position(|&b| b == 0).unwrap_or(field.len());
    String::from_utf8(field[..end].to_vec())
        .map_err(|_| JvError::UnsafeArchive { reason: "not_utf8" })
}

fn read_exact_or_eof<R: Read>(r: &mut R, buf: &mut [u8]) -> JvResult<bool> {
    let mut got = 0;
    while got < buf.len() {
        match r.read(&mut buf[got..]) {
            Ok(0) if got == 0 => return Ok(false),
            Ok(0) => return Err(JvError::ArchiveRead),
            Ok(n) => got += n,
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
            Err(_) => return Err(JvError::ArchiveRead),
        }
    }
    Ok(true)
}

fn read_data<R: Read>(r: &mut R, size: u64, cap: usize) -> JvResult<Vec<u8>> {
    if size as usize > cap {
        return Err(JvError::UnsafeArchive {
            reason: "header_too_large",
        });
    }
    let mut data = vec![0u8; size as usize];
    if !read_exact_or_eof(r, &mut data)? && size > 0 {
        return Err(JvError::ArchiveRead);
    }
    skip_padding(r, size)?;
    Ok(data)
}

fn skip_padding<R: Read>(r: &mut R, size: u64) -> JvResult<()> {
    let pad = (512 - (size % 512)) % 512;
    let mut buf = [0u8; 512];
    if pad > 0 && !read_exact_or_eof(r, &mut buf[..pad as usize])? {
        return Err(JvError::ArchiveRead);
    }
    Ok(())
}

/// PAX-poster: «<lengde> <nøkkel>=<verdi>\n».
fn parse_pax(data: &[u8]) -> JvResult<Vec<(String, String)>> {
    let mut out = Vec::new();
    let mut rest = data;
    while !rest.is_empty() {
        let sp = rest
            .iter()
            .position(|&b| b == b' ')
            .ok_or(JvError::ArchiveRead)?;
        let len: usize = std::str::from_utf8(&rest[..sp])
            .ok()
            .and_then(|s| s.parse().ok())
            .ok_or(JvError::ArchiveRead)?;
        if len <= sp + 1 || len > rest.len() {
            return Err(JvError::ArchiveRead);
        }
        let rec = &rest[sp + 1..len - 1];
        let eq = rec
            .iter()
            .position(|&b| b == b'=')
            .ok_or(JvError::ArchiveRead)?;
        let key = String::from_utf8(rec[..eq].to_vec()).map_err(|_| JvError::ArchiveRead)?;
        // Verdiene kan være binære (SCHILY.xattr.*); bare stier og størrelse leses.
        let val = if matches!(key.as_str(), "path" | "linkpath" | "size") {
            String::from_utf8(rec[eq + 1..].to_vec())
                .map_err(|_| JvError::UnsafeArchive { reason: "not_utf8" })?
        } else {
            String::new()
        };
        out.push((key, val));
        rest = &rest[len..];
    }
    Ok(out)
}

/// Leser en tar-strøm (ustar/pax/GNU) og skriver den kontrollert til `dest`.
pub fn extract_tar_stream<R: Read>(mut r: R, dest: &Path) -> JvResult<ExtractStats> {
    let mut stats = ExtractStats::default();
    let mut seen: HashSet<Vec<String>> = HashSet::new();
    let mut symlinks: HashSet<Vec<String>> = HashSet::new();
    let mut pax_path: Option<String> = None;
    let mut pax_link: Option<String> = None;
    let mut pax_size: Option<u64> = None;
    let mut gnu_name: Option<String> = None;
    let mut gnu_link: Option<String> = None;
    let mut zero_blocks = 0;
    let mut entries = 0usize;
    let mut header = [0u8; 512];
    loop {
        if !read_exact_or_eof(&mut r, &mut header)? {
            break;
        }
        if header.iter().all(|&b| b == 0) {
            zero_blocks += 1;
            if zero_blocks == 2 {
                break;
            }
            continue;
        }
        zero_blocks = 0;
        // Sjekksum: summen av bytene med feltet som mellomrom.
        let want = octal(&header[148..156])?;
        let sum: u64 = header
            .iter()
            .enumerate()
            .map(|(i, &b)| {
                if (148..156).contains(&i) {
                    32
                } else {
                    b as u64
                }
            })
            .sum();
        if want != sum {
            return Err(JvError::ArchiveRead);
        }
        entries += 1;
        if entries > MAX_ENTRIES {
            return Err(JvError::UnsafeArchive {
                reason: "too_many_entries",
            });
        }
        let typeflag = header[156];
        let mut size = octal(&header[124..136])?;
        match typeflag {
            b'x' => {
                let data = read_data(&mut r, size, 1 << 20)?;
                for (k, v) in parse_pax(&data)? {
                    match k.as_str() {
                        "path" => pax_path = Some(v),
                        "linkpath" => pax_link = Some(v),
                        "size" => pax_size = Some(v.parse().map_err(|_| JvError::ArchiveRead)?),
                        _ => {}
                    }
                }
                continue;
            }
            b'g' => {
                // Globale PAX-poster: ingen av dem endrer stier her.
                read_data(&mut r, size, 1 << 20)?;
                continue;
            }
            b'L' => {
                gnu_name = Some(cstr(&read_data(&mut r, size, 1 << 16)?)?);
                continue;
            }
            b'K' => {
                gnu_link = Some(cstr(&read_data(&mut r, size, 1 << 16)?)?);
                continue;
            }
            _ => {}
        }
        if let Some(s) = pax_size.take() {
            size = s;
        }
        let name = match (pax_path.take(), gnu_name.take()) {
            (Some(p), _) => p,
            (None, Some(g)) => g,
            (None, None) => {
                let base = cstr(&header[0..100])?;
                let prefix = if &header[257..262] == b"ustar" {
                    cstr(&header[345..500])?
                } else {
                    String::new()
                };
                if prefix.is_empty() {
                    base
                } else {
                    format!("{prefix}/{base}")
                }
            }
        };
        let link = match (pax_link.take(), gnu_link.take()) {
            (Some(l), _) => l,
            (None, Some(g)) => g,
            (None, None) => cstr(&header[157..257])?,
        };
        let mode = octal(&header[100..108])? as u32;
        let parts = checked_parts(&name)?;
        // Ingen sti får gå gjennom en symlenke fra arkivet.
        for i in 1..parts.len() {
            if symlinks.contains(&parts[..i].to_vec()) {
                return Err(JvError::UnsafeArchive {
                    reason: "through_symlink",
                });
            }
        }
        let is_dir = typeflag == b'5';
        if !seen.insert(parts.clone()) && !is_dir {
            return Err(JvError::UnsafeArchive {
                reason: "duplicate",
            });
        }
        let path: PathBuf = parts.iter().fold(dest.to_path_buf(), |p, s| p.join(s));
        debug_assert!(path
            .components()
            .all(|c| !matches!(c, Component::ParentDir)));
        match typeflag {
            b'0' | 0 | b'7' => {
                stats.bytes += size;
                if stats.bytes > MAX_TOTAL_BYTES {
                    return Err(JvError::UnsafeArchive {
                        reason: "too_large",
                    });
                }
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)?;
                }
                let mut opts = OpenOptions::new();
                opts.write(true).create_new(true);
                #[cfg(not(unix))]
                let _ = mode;
                #[cfg(unix)]
                {
                    use std::os::unix::fs::OpenOptionsExt;
                    opts.mode(if mode & 0o111 != 0 { 0o755 } else { 0o644 });
                }
                let mut f = opts.open(&path).map_err(|e| {
                    if e.kind() == std::io::ErrorKind::AlreadyExists {
                        JvError::UnsafeArchive { reason: "exists" }
                    } else {
                        e.into()
                    }
                })?;
                let mut left = size;
                let mut buf = vec![0u8; 256 * 1024];
                while left > 0 {
                    let want = left.min(buf.len() as u64) as usize;
                    if !read_exact_or_eof(&mut r, &mut buf[..want])? {
                        return Err(JvError::ArchiveRead);
                    }
                    f.write_all(&buf[..want])?;
                    left -= want as u64;
                }
                skip_padding(&mut r, size)?;
                stats.files += 1;
            }
            b'5' => {
                fs::create_dir_all(&path)?;
                stats.dirs += 1;
            }
            b'2' => {
                if cfg!(windows) {
                    return Err(JvError::UnsafeArchive {
                        reason: "symlink_on_windows",
                    });
                }
                if !symlink_stays_inside(&parts, &link) {
                    return Err(JvError::UnsafeArchive {
                        reason: "symlink_outside",
                    });
                }
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)?;
                }
                #[cfg(unix)]
                std::os::unix::fs::symlink(&link, &path).map_err(|e| {
                    if e.kind() == std::io::ErrorKind::AlreadyExists {
                        JvError::UnsafeArchive { reason: "exists" }
                    } else {
                        e.into()
                    }
                })?;
                symlinks.insert(parts);
                stats.symlinks += 1;
                skip_padding(&mut r, 0)?;
            }
            b'1' => return Err(JvError::UnsafeArchive { reason: "hardlink" }),
            _ => {
                return Err(JvError::UnsafeArchive {
                    reason: "special_file",
                })
            }
        }
    }
    Ok(stats)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    /// Lager en ustar-header (for tester av farlige arkiv).
    pub fn header(name: &str, typeflag: u8, size: u64, link: &str, mode: u32) -> [u8; 512] {
        let mut h = [0u8; 512];
        h[..name.len()].copy_from_slice(name.as_bytes());
        let m = format!("{mode:07o}\0");
        h[100..108].copy_from_slice(m.as_bytes());
        h[108..116].copy_from_slice(b"0000000\0");
        h[116..124].copy_from_slice(b"0000000\0");
        let s = format!("{size:011o}\0");
        h[124..136].copy_from_slice(s.as_bytes());
        h[136..148].copy_from_slice(b"00000000000\0");
        h[156] = typeflag;
        h[157..157 + link.len()].copy_from_slice(link.as_bytes());
        h[257..263].copy_from_slice(b"ustar\0");
        h[263..265].copy_from_slice(b"00");
        h[148..156].copy_from_slice(b"        ");
        let sum: u32 = h.iter().map(|&b| b as u32).sum();
        let c = format!("{sum:06o}\0 ");
        h[148..156].copy_from_slice(c.as_bytes());
        h
    }

    /// En tar-strøm av (navn, type, innhold, lenkemål).
    pub fn tar(entries: &[(&str, u8, &[u8], &str)]) -> Vec<u8> {
        let mut out = Vec::new();
        for (name, t, data, link) in entries {
            let mode = if *t == b'5' { 0o755 } else { 0o644 };
            out.extend_from_slice(&header(name, *t, data.len() as u64, link, mode));
            out.extend_from_slice(data);
            let pad = (512 - data.len() % 512) % 512;
            out.extend(std::iter::repeat_n(0u8, pad));
        }
        out.extend(std::iter::repeat_n(0u8, 1024));
        out
    }

    fn tmp() -> PathBuf {
        static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let d = std::env::temp_dir().join(format!(
            "jv-arkivtest-{}-{}-{}",
            std::process::id(),
            N.fetch_add(1, std::sync::atomic::Ordering::SeqCst),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn reason(r: JvResult<ExtractStats>) -> &'static str {
        match r {
            Err(JvError::UnsafeArchive { reason }) => reason,
            other => panic!("ventet UnsafeArchive, fikk {other:?}"),
        }
    }

    #[test]
    fn plain_archive_is_extracted() {
        let d = tmp();
        let t = tar(&[("a/", b'5', b"", ""), ("a/b.txt", b'0', b"hei", "")]);
        let s = extract_tar_stream(&t[..], &d).unwrap();
        assert_eq!((s.files, s.dirs, s.symlinks), (1, 1, 0));
        assert_eq!(fs::read(d.join("a").join("b.txt")).unwrap(), b"hei");
        fs::remove_dir_all(&d).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn symlink_inside_is_kept() {
        let d = tmp();
        let t = tar(&[
            ("a/", b'5', b"", ""),
            ("a/b.txt", b'0', b"hei", ""),
            ("a/lenke", b'2', b"", "b.txt"),
            ("c/lenke2", b'2', b"", "../a/b.txt"),
        ]);
        let s = extract_tar_stream(&t[..], &d).unwrap();
        assert_eq!((s.files, s.dirs, s.symlinks), (1, 1, 2));
        assert_eq!(fs::read(d.join("a/lenke")).unwrap(), b"hei");
        assert_eq!(fs::read(d.join("c/lenke2")).unwrap(), b"hei");
        fs::remove_dir_all(&d).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn symlink_is_rejected_on_windows() {
        let d = tmp();
        let t = tar(&[("lenke", b'2', b"", "b.txt")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "symlink_on_windows");
        fs::remove_dir_all(&d).unwrap();
    }

    /// Windows-veien: en .zip laget av tar.exe pakkes ut gjennom `extract`.
    #[cfg(windows)]
    #[test]
    fn windows_zip_through_system_tar() {
        let src = tmp();
        fs::create_dir_all(src.join("bin")).unwrap();
        fs::write(src.join("bin").join("jv.txt"), b"hei fra zip").unwrap();
        let arch = tmp().join("pakke.zip");
        let ok = Command::new(system_tar())
            .arg("-a")
            .arg("-cf")
            .arg(&arch)
            .arg("-C")
            .arg(&src)
            .arg("bin")
            .status()
            .unwrap()
            .success();
        assert!(ok);
        let d = tmp();
        let s = extract(&arch, &d).unwrap();
        assert_eq!(s.files, 1);
        assert_eq!(
            fs::read(d.join("bin").join("jv.txt")).unwrap(),
            b"hei fra zip"
        );
    }

    #[test]
    fn dotdot_is_rejected() {
        let d = tmp();
        let t = tar(&[("../ut.txt", b'0', b"x", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "dotdot");
        let t = tar(&[("a/../../ut.txt", b'0', b"x", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "dotdot");
        assert!(!d.parent().unwrap().join("ut.txt").exists());
        fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn absolute_path_is_rejected() {
        let d = tmp();
        let t = tar(&[("/tmp/jv-ut.txt", b'0', b"x", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "absolute");
        let t = tar(&[("C:/Windows/x", b'0', b"x", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "bad_char");
        let t = tar(&[("a\\..\\..\\x", b'0', b"x", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "bad_char");
        fs::remove_dir_all(&d).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn symlink_out_is_rejected() {
        let d = tmp();
        for target in ["../../etc", "/etc", "a/../../x", "../"] {
            let t = tar(&[("lenke", b'2', b"", target)]);
            assert_eq!(
                reason(extract_tar_stream(&t[..], &d)),
                "symlink_outside",
                "{target}"
            );
        }
        fs::remove_dir_all(&d).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn path_through_symlink_is_rejected() {
        // Klassisk angrep: «a» → «.», så «a/a/…» – eller en lenke ut og så skriving gjennom den.
        let d = tmp();
        let t = tar(&[("a", b'2', b"", "."), ("a/x.txt", b'0', b"x", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "through_symlink");
        fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn hardlink_device_and_duplicate_are_rejected() {
        let d = tmp();
        let t = tar(&[("h", b'1', b"", "x")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "hardlink");
        let t = tar(&[("dev", b'3', b"", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d)), "special_file");
        let d2 = tmp();
        let t = tar(&[("x", b'0', b"1", ""), ("x", b'0', b"2", "")]);
        assert_eq!(reason(extract_tar_stream(&t[..], &d2)), "duplicate");
        fs::remove_dir_all(&d).unwrap();
        fs::remove_dir_all(&d2).unwrap();
    }

    #[test]
    fn bad_checksum_is_a_read_error() {
        let d = tmp();
        let mut t = tar(&[("x", b'0', b"1", "")]);
        t[0] = b'y';
        assert_eq!(extract_tar_stream(&t[..], &d), Err(JvError::ArchiveRead));
        fs::remove_dir_all(&d).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn setuid_is_dropped() {
        use std::os::unix::fs::PermissionsExt;
        let d = tmp();
        let mut t = Vec::new();
        t.extend_from_slice(&header("s", b'0', 1, "", 0o4755));
        t.extend_from_slice(b"x");
        t.extend(std::iter::repeat_n(0u8, 511 + 1024));
        extract_tar_stream(&t[..], &d).unwrap();
        let mode = fs::metadata(d.join("s")).unwrap().permissions().mode();
        assert_eq!(mode & 0o7777, 0o755);
        fs::remove_dir_all(&d).unwrap();
    }

    /// Hele veien gjennom systemets tar: et .tar.gz laget av /usr/bin/tar med
    /// en symlenke ut skal avvises.
    #[cfg(target_os = "macos")]
    #[test]
    fn system_tar_path_rejects_symlink_out() {
        let src = tmp();
        std::os::unix::fs::symlink("../../../etc", src.join("ut")).unwrap();
        let arch = tmp().join("ond.tar.gz");
        let ok = Command::new("/usr/bin/tar")
            .arg("-czf")
            .arg(&arch)
            .arg("-C")
            .arg(&src)
            .arg("ut")
            .status()
            .unwrap()
            .success();
        assert!(ok);
        let d = tmp();
        assert_eq!(reason(extract(&arch, &d)), "symlink_outside");
        // Og et arkiv med ../ i stien (bsdtar -s skriver navnet om).
        fs::write(src.join("f"), b"x").unwrap();
        let arch2 = arch.with_file_name("ond2.tar.gz");
        Command::new("/usr/bin/tar")
            .args(["-czf"])
            .arg(&arch2)
            .arg("-C")
            .arg(&src)
            .args(["-s", ",^f$,../../f,", "f"])
            .status()
            .unwrap();
        let d2 = tmp();
        assert_eq!(reason(extract(&arch2, &d2)), "dotdot");
        for p in [&src, &d, &d2, &arch.parent().unwrap().to_path_buf()] {
            let _ = fs::remove_dir_all(p);
        }
    }
}
