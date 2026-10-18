// Ingen konsollvindu på Windows i utgivelsesbygg.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    lla_verktoykasse_lib::run();
}
