export type Os = "mac" | "windows" | "other";

/** Operativsystemet ut fra `navigator.userAgent`. */
export function detectOs(userAgent: string): Os {
  if (/Windows/i.test(userAgent)) return "windows";
  if (/Macintosh|Mac OS X/i.test(userAgent)) return "mac";
  return "other";
}
