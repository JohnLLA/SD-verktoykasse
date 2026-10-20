// Registeroppføringen for «metadata». Skjermen er den felles i `../jv`.

import { defineJvTool } from "../jv";
import { schema } from "./schema";

export const metadata = defineJvTool(schema);
