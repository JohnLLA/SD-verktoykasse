// Registeroppføringen for «redact». Skjermen er den felles i `../jv`.

import { defineJvTool } from "../jv";
import { schema } from "./schema";

export const redact = defineJvTool(schema);
