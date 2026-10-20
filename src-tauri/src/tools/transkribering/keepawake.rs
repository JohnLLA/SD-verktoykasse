//! Hindrer at maskinen går i dvale mens en jobb kjører.
//!
//! - macOS: en IOKit-påstand `PreventUserIdleSystemSleep`. Det er samme
//!   mekanisme som `NSProcessInfo beginActivity(.idleSystemSleepDisabled)`
//!   bruker under panseret, men kan kalles fra Rust uten Objective-C-crates.
//! - Windows: `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`.
//!   Gjelder tråden som kaller, så vakten må lages og slippes i jobbtråden
//!   (den er derfor ikke `Send`).
//!
//! Skjermen får slukke; bare systemdvale hindres. Frigis når vakten slippes,
//! også ved feil, avbrudd og panikk.

use std::marker::PhantomData;

pub struct KeepAwake {
    #[allow(dead_code)]
    inner: platform::Handle,
    _not_send: PhantomData<*const ()>,
}

impl KeepAwake {
    /// Navnet vises i `pmset -g assertions`. Ingen filnavn. Bare ASCII:
    /// pmset viser ikke æøå riktig.
    pub const REASON: &'static str = "SD-Verktoy: transkribering";

    /// Prøver å hindre dvale. Feiler det, kjører jobben likevel.
    pub fn start() -> Option<KeepAwake> {
        platform::Handle::acquire(Self::REASON).map(|inner| KeepAwake {
            inner,
            _not_send: PhantomData,
        })
    }
}

#[cfg(target_os = "macos")]
mod platform {
    use std::ffi::{c_char, c_void, CString};

    type CFStringRef = *const c_void;
    type CFAllocatorRef = *const c_void;
    type IOPMAssertionID = u32;
    const K_CF_STRING_ENCODING_UTF8: u32 = 0x0800_0100;
    const K_IOPM_ASSERTION_LEVEL_ON: u32 = 255;

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        fn CFStringCreateWithCString(
            alloc: CFAllocatorRef,
            cstr: *const c_char,
            encoding: u32,
        ) -> CFStringRef;
        fn CFRelease(cf: *const c_void);
    }

    #[link(name = "IOKit", kind = "framework")]
    extern "C" {
        fn IOPMAssertionCreateWithName(
            assertion_type: CFStringRef,
            level: u32,
            name: CFStringRef,
            id: *mut IOPMAssertionID,
        ) -> i32;
        fn IOPMAssertionRelease(id: IOPMAssertionID) -> i32;
    }

    fn cfstr(s: &str) -> Option<CFStringRef> {
        let c = CString::new(s).ok()?;
        // SAFETY: gyldig nullterminert UTF-8; standard allokator (NULL).
        let r = unsafe {
            CFStringCreateWithCString(std::ptr::null(), c.as_ptr(), K_CF_STRING_ENCODING_UTF8)
        };
        (!r.is_null()).then_some(r)
    }

    pub struct Handle(IOPMAssertionID);

    impl Handle {
        pub fn acquire(reason: &str) -> Option<Handle> {
            let kind = cfstr("PreventUserIdleSystemSleep")?;
            let Some(name) = cfstr(reason) else {
                // SAFETY: `kind` er laget av CFStringCreate over.
                unsafe { CFRelease(kind) };
                return None;
            };
            let mut id: IOPMAssertionID = 0;
            // SAFETY: gyldige CFString-er og peker til `id`.
            let r = unsafe {
                IOPMAssertionCreateWithName(kind, K_IOPM_ASSERTION_LEVEL_ON, name, &mut id)
            };
            // SAFETY: begge er laget av CFStringCreate over og brukes ikke mer.
            unsafe {
                CFRelease(kind);
                CFRelease(name);
            }
            (r == 0).then_some(Handle(id))
        }
    }

    impl Drop for Handle {
        fn drop(&mut self) {
            // SAFETY: ID-en kommer fra IOPMAssertionCreateWithName.
            unsafe { IOPMAssertionRelease(self.0) };
        }
    }
}

#[cfg(windows)]
mod platform {
    const ES_CONTINUOUS: u32 = 0x8000_0000;
    const ES_SYSTEM_REQUIRED: u32 = 0x0000_0001;

    #[link(name = "kernel32")]
    extern "system" {
        fn SetThreadExecutionState(flags: u32) -> u32;
    }

    pub struct Handle;

    impl Handle {
        pub fn acquire(_reason: &str) -> Option<Handle> {
            // SAFETY: enkelt Win32-kall uten pekere.
            let prev = unsafe { SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) };
            (prev != 0).then_some(Handle)
        }
    }

    impl Drop for Handle {
        fn drop(&mut self) {
            // SAFETY: som over. Nullstiller for denne tråden.
            unsafe { SetThreadExecutionState(ES_CONTINUOUS) };
        }
    }
}

#[cfg(not(any(target_os = "macos", windows)))]
mod platform {
    pub struct Handle;
    impl Handle {
        pub fn acquire(_reason: &str) -> Option<Handle> {
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[cfg(any(target_os = "macos", windows))]
    fn acquire_and_release() {
        let g = KeepAwake::start();
        assert!(g.is_some());
        #[cfg(target_os = "macos")]
        {
            let has = || {
                std::process::Command::new("pmset")
                    .args(["-g", "assertions"])
                    .output()
                    .map(|o| String::from_utf8_lossy(&o.stdout).contains(KeepAwake::REASON))
                    .unwrap_or(false)
            };
            assert!(has(), "påstanden finnes ikke i pmset");
            drop(g);
            assert!(!has(), "påstanden ble ikke frigitt");
        }
        #[cfg(windows)]
        drop(g);
    }
}
