import { defineConfig } from "vitest/config";

// Frontend for Tauri. Ingen eksterne skript, fonter eller CDN-er: alt i
// index.html peker på filer i denne mappen, og Vite pakker dem i dist/.
export default defineConfig({
  clearScreen: false,
  server: { port: 1420, strictPort: true, host: "localhost" },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // Eldste støttede webvisning: Safari 16 (macOS 13) og WebView2 (Windows 10/11).
    target: ["es2022", "safari15", "chrome105"],
    // Ingen innebygde (inline) skript eller stiler, siden CSP er streng.
    assetsInlineLimit: 0,
    cssCodeSplit: false,
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    // Gjør at `?raw`-import av .css gir selve teksten (kontrasttesten leser theme.css).
    css: { include: [/theme\.css/] },
  },
});
