// Registeroppføringen for «datawrapper». Egen skjerm (valg, forhåndsvisning,
// kopiering), men samme nedlasting, økt og kjøring som de andre i `../jv`.

import { defineJvTool } from "../jv";
import { createDatawrapperScreen } from "./view";
import { schema } from "./schema";

export const datawrapper = defineJvTool(schema, createDatawrapperScreen);
