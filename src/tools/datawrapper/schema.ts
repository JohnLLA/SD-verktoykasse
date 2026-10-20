// Klargjør for Datawrapper: foreløpig bare filtypene. Skjemaet og visningen
// (ark, tabell, sumrader, bytt, kolonner, forhåndsvisning og kopiering) lages
// av grensesnittbyggeren (docs/spesifikasjon-datawrapper.md, «Grensesnitt»).
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
