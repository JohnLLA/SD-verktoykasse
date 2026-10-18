//! Maskininfo: CPU-instruksjoner, fysiske kjerner og minne.
//!
//! Uten nye crates: `is_x86_feature_detected!` fra std, og små FFI-kall mot
//! operativsystemet (`sysctlbyname` på macOS, `kernel32` på Windows).

use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct SystemInfo {
    /// `false` hvis prosessoren mangler noe whisper.cpp er bygget for.
    pub cpu_supported: bool,
    /// Instruksjonene som mangler (f.eks. `["avx2", "fma"]`).
    pub missing_cpu_features: Vec<String>,
    pub physical_cores: usize,
    /// Trådene whisper får.
    pub whisper_threads: usize,
    pub total_memory_bytes: Option<u64>,
    /// `metal` på Mac, `cpu` ellers.
    pub accelerator: &'static str,
}

/// Instruksjoner Windows-bygget er laget for (`.cargo/config.toml`:
/// AVX, AVX2, FMA, F16C, BMI2). Mangler én, krasjer whisper.cpp med
/// «illegal instruction». Vi sjekker før modellen lastes.
pub fn missing_cpu_features() -> Vec<String> {
    #[cfg(target_arch = "x86_64")]
    {
        let mut v = Vec::new();
        if !std::arch::is_x86_feature_detected!("avx") {
            v.push("avx".to_string());
        }
        if !std::arch::is_x86_feature_detected!("avx2") {
            v.push("avx2".to_string());
        }
        if !std::arch::is_x86_feature_detected!("fma") {
            v.push("fma".to_string());
        }
        if !std::arch::is_x86_feature_detected!("f16c") {
            v.push("f16c".to_string());
        }
        if !std::arch::is_x86_feature_detected!("bmi2") {
            v.push("bmi2".to_string());
        }
        v
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        Vec::new()
    }
}

/// Fysiske kjerner. På Apple Silicon: ytelseskjernene.
pub fn physical_cores() -> usize {
    let n = platform::physical_cores().unwrap_or(0);
    if n > 0 {
        return n;
    }
    // Reserve: logiske kjerner, halvert når det er flere enn 4 (antar hyperthreading).
    let logical = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4);
    if logical > 4 {
        logical / 2
    } else {
        logical
    }
}

/// Antall tråder til whisper: aldri flere enn fysiske kjerner (ggml-trådene
/// venter aktivt, og på 2 vCPU ble 4 tråder katastrofalt tregere), og høyst 8.
pub fn whisper_threads(requested: Option<usize>) -> usize {
    let cores = physical_cores().max(1);
    let max = cores.min(8);
    requested.unwrap_or(max).clamp(1, cores)
}

pub fn total_memory_bytes() -> Option<u64> {
    platform::total_memory()
}

pub fn info() -> SystemInfo {
    let missing = missing_cpu_features();
    SystemInfo {
        cpu_supported: missing.is_empty(),
        missing_cpu_features: missing,
        physical_cores: physical_cores(),
        whisper_threads: whisper_threads(None),
        total_memory_bytes: total_memory_bytes(),
        accelerator: if cfg!(target_os = "macos") {
            "metal"
        } else {
            "cpu"
        },
    }
}

#[cfg(target_os = "macos")]
mod platform {
    use std::ffi::{c_char, c_int, c_void, CStr};

    extern "C" {
        fn sysctlbyname(
            name: *const c_char,
            oldp: *mut c_void,
            oldlenp: *mut usize,
            newp: *mut c_void,
            newlen: usize,
        ) -> c_int;
    }

    fn read<T: Default + Copy>(name: &CStr) -> Option<T> {
        let mut v = T::default();
        let mut len = std::mem::size_of::<T>();
        // SAFETY: `v` er gyldig for `len` byte, og navnet er en nullterminert streng.
        let r = unsafe {
            sysctlbyname(
                name.as_ptr(),
                &mut v as *mut T as *mut c_void,
                &mut len,
                std::ptr::null_mut(),
                0,
            )
        };
        (r == 0 && len == std::mem::size_of::<T>()).then_some(v)
    }

    pub fn physical_cores() -> Option<usize> {
        read::<i32>(c"hw.perflevel0.physicalcpu")
            .or_else(|| read::<i32>(c"hw.physicalcpu"))
            .filter(|n| *n > 0)
            .map(|n| n as usize)
    }

    pub fn total_memory() -> Option<u64> {
        read::<u64>(c"hw.memsize")
    }
}

#[cfg(windows)]
mod platform {
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct LogicalProcessorInfo {
        processor_mask: usize,
        relationship: u32,
        // Union på 16 byte (justert til 8).
        _union: [u64; 2],
    }

    #[repr(C)]
    struct MemoryStatusEx {
        length: u32,
        memory_load: u32,
        total_phys: u64,
        avail_phys: u64,
        total_page_file: u64,
        avail_page_file: u64,
        total_virtual: u64,
        avail_virtual: u64,
        avail_extended_virtual: u64,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetLogicalProcessorInformation(
            buffer: *mut LogicalProcessorInfo,
            length: *mut u32,
        ) -> i32;
        fn GlobalMemoryStatusEx(buffer: *mut MemoryStatusEx) -> i32;
    }

    const RELATION_PROCESSOR_CORE: u32 = 0;

    pub fn physical_cores() -> Option<usize> {
        let mut len: u32 = 0;
        // SAFETY: første kall med null-buffer gir bare nødvendig lengde.
        unsafe { GetLogicalProcessorInformation(std::ptr::null_mut(), &mut len) };
        let size = std::mem::size_of::<LogicalProcessorInfo>();
        if len == 0 || size != 32 {
            return None;
        }
        let n = len as usize / size + 1;
        let mut buf = vec![
            LogicalProcessorInfo {
                processor_mask: 0,
                relationship: u32::MAX,
                _union: [0; 2]
            };
            n
        ];
        let mut len2 = (n * size) as u32;
        // SAFETY: bufferet har plass til `len2` byte.
        let ok = unsafe { GetLogicalProcessorInformation(buf.as_mut_ptr(), &mut len2) };
        if ok == 0 {
            return None;
        }
        let used = len2 as usize / size;
        let cores = buf[..used.min(n)]
            .iter()
            .filter(|e| e.relationship == RELATION_PROCESSOR_CORE)
            .count();
        (cores > 0).then_some(cores)
    }

    pub fn total_memory() -> Option<u64> {
        let mut m = MemoryStatusEx {
            length: std::mem::size_of::<MemoryStatusEx>() as u32,
            memory_load: 0,
            total_phys: 0,
            avail_phys: 0,
            total_page_file: 0,
            avail_page_file: 0,
            total_virtual: 0,
            avail_virtual: 0,
            avail_extended_virtual: 0,
        };
        // SAFETY: strukturen har riktig størrelse og `length` er satt.
        let ok = unsafe { GlobalMemoryStatusEx(&mut m) };
        (ok != 0).then_some(m.total_phys)
    }
}

#[cfg(not(any(target_os = "macos", windows)))]
mod platform {
    pub fn physical_cores() -> Option<usize> {
        None
    }
    pub fn total_memory() -> Option<u64> {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn threads_never_exceed_physical_cores() {
        let cores = physical_cores();
        assert!(cores >= 1);
        assert!(whisper_threads(None) <= cores);
        assert!(whisper_threads(None) <= 8);
        assert_eq!(whisper_threads(Some(10_000)), cores);
        assert_eq!(whisper_threads(Some(0)), 1);
    }

    #[test]
    fn platform_queries_work() {
        let i = info();
        if cfg!(any(target_os = "macos", windows)) {
            assert!(i.total_memory_bytes.unwrap_or(0) > 1 << 30);
            assert!(platform::physical_cores().is_some());
        }
        // CI-maskinene (og alle støttede maskiner) har det bygget krever.
        assert!(i.cpu_supported, "mangler {:?}", i.missing_cpu_features);
    }
}
