// Verktøyregisteret. Menyen i skallet lages herfra. Et nytt verktøy legges til
// med én linje her (og én i `src-tauri/src/tools/mod.rs`).

import { transkribering } from "./transkribering";
import type { ToolDefinition } from "./types";

export const tools: readonly ToolDefinition[] = [transkribering];
