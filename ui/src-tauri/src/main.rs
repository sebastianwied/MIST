// MIST UI — Tauri shell
// The frontend connects directly to the Python core via WebSocket.
// This Rust backend provides the native window and can optionally
// manage the core process lifecycle.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
