// Filnavn og filtyper. Rene funksjoner. Filnavn brukes bare i grensesnittet
// og sendes aldri til logg (regel 2).

/** Lyd og video som Rust-kjernen leser (spesifikasjonen, «Filer inn»). */
export const SUPPORTED_EXTENSIONS = [
  "mp3",
  "m4a",
  "aac",
  "wav",
  "flac",
  "ogg",
  "oga",
  "mp4",
  "mov",
] as const;

/** Filendelsene i filvelgeren (uten punktum). */
export const DIALOG_EXTENSIONS: string[] = [...SUPPORTED_EXTENSIONS];

/** Siste del av en sti, med både `/` og `\` som skille. */
export function fileName(path: string): string {
  const parts = path.split(/[\\/]/).filter((p) => p.length > 0);
  return parts[parts.length - 1] ?? path;
}

/** Filendelsen i små bokstaver, uten punktum. Tom hvis den mangler. */
export function fileExtension(path: string): string {
  const name = fileName(path);
  const dot = name.lastIndexOf(".");
  if (dot <= 0 || dot === name.length - 1) return "";
  return name.slice(dot + 1).toLowerCase();
}

export function isSupportedExtension(path: string): boolean {
  return (SUPPORTED_EXTENSIONS as readonly string[]).includes(fileExtension(path));
}
