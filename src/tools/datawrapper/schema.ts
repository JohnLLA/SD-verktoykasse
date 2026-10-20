// Klargjør for Datawrapper: filtypene og at verktøyet tar én fil. Valgene
// (ark, tabell, sumrader, bytt, kolonner) styres av egen skjerm (`view.ts`,
// `controller.ts`) og blir til forespørsler i `request.ts`, så `fields` er tom.
// Rust-hvitelisten (args.rs) tar `command` `analyser`/`lag` og valgene
// `sheet`, `table`, `with_sums`, `transpose`, `remove_columns` og `csv_file`.

import type { ToolSchema } from "../jv/schema";

export const schema: ToolSchema = {
  id: "datawrapper",
  icon: "table",
  extensions: ["xlsx", "xlsm", "xls", "csv", "txt"],
  exactFiles: 1,
  fields: [],
};
