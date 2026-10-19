// Alle brukertekster i appen, på bokmål (regel 10). Ingen tekst står i
// komponentene. Nynorsk grensesnitt er ønsket senere (docs/senere.md): da lages
// en `nn.ts` med samme form (`Texts`), og `t` velges ved oppstart.
//
// Skriv som til en travel journalist: korte setninger, ingen fagord.

import type { CoreError, ErrorCode, HeaderLabels } from "../tools/transkribering/api";

export interface ErrorText {
  /** Hva som skjedde. */
  title: string;
  /** Hva brukeren kan gjøre. Kan være tom. */
  hint: string;
}

type ErrorTexts = { [K in ErrorCode]: (e: Extract<CoreError, { code: K }>) => ErrorText };

const SUPPORTED_FORMATS = "mp3, m4a, wav, flac, ogg, mp4 og mov";

const something_went_wrong: ErrorText = {
  title: "Noe gikk galt i appen",
  hint: "Prøv igjen. Skjer det igjen, start appen på nytt og ta kontakt med LLA.",
};

const errors: ErrorTexts = {
  file_not_found: () => ({
    title: "Fant ikke filen",
    hint: "Den kan være flyttet eller slettet, eller ligge på en disk som ikke er koblet til. Legg den til på nytt.",
  }),
  unsupported_format: (e) => ({
    title: "Filformatet støttes ikke",
    hint:
      (e.format ? `Filen er i formatet «${e.format}». ` : "") +
      `Verktøyet leser ${SUPPORTED_FORMATS}. ` +
      "Gjør filen om til mp3 eller wav, for eksempel i VLC eller Audacity, og legg den til på nytt.",
  }),
  no_audio_track: () => ({
    title: "Filen har ikke lyd",
    hint: "Vi fant ikke noe lydspor i filen. Sjekk at det er riktig fil, eller lagre den på nytt som mp3 eller wav.",
  }),
  empty_audio: () => ({
    title: "Filen er tom",
    hint: "Det er ingen lyd i filen. Sjekk at det er riktig fil.",
  }),
  decode_failed: () => ({
    title: "Filen kunne ikke leses",
    hint: "Den kan være skadet, for eksempel hvis opptaket ble avbrutt. Prøv å spille den av først. Hjelper ikke det, kan du lagre den på nytt som mp3 eller wav.",
  }),
  unknown_model: () => something_went_wrong,
  model_missing: () => ({
    title: "Modellen er ikke lastet ned",
    hint: "Last den ned og prøv igjen.",
  }),
  model_load_failed: () => ({
    title: "Modellen kunne ikke åpnes",
    hint: "Filen kan være skadet. Slett modellen under Innstillinger, last den ned på nytt og prøv igjen.",
  }),
  model_in_shared_folder: () => ({
    title: "Modellen ligger i din egen modellmappe",
    hint: "Den kan ikke slettes herfra. Slett filen i mappen selv, eller gå tilbake til standardmappen.",
  }),
  invalid_catalog: () => something_went_wrong,
  host_not_allowed: () => something_went_wrong,
  http_status: () => ({
    title: "Nedlastingen ble avvist",
    hint: "Tjenesten svarte ikke som den skulle. Prøv igjen om litt.",
  }),
  network: () => ({
    title: "Ingen nettforbindelse",
    hint: "Modellen lastes ned fra internett. Sjekk at du er på nett og prøv igjen. Det som er lastet ned, beholdes, så nedlastingen fortsetter der den slapp.",
  }),
  checksum_mismatch: () => ({
    title: "Nedlastingen ble skadet",
    hint: "Filen ble ikke lastet ned riktig, og er slettet. Prøv å laste ned på nytt.",
  }),
  size_mismatch: () => ({
    title: "Nedlastingen ble ikke fullstendig",
    hint: "Prøv å laste ned på nytt.",
  }),
  disk_full: () => ({
    title: "Det er ikke nok plass på disken",
    hint: "Frigjør plass og prøv igjen. Modeller du ikke bruker, kan slettes under Innstillinger.",
  }),
  cpu_unsupported: (e) => ({
    title: "Denne maskinen er for gammel til å transkribere",
    hint:
      "Prosessoren mangler en funksjon som trengs" +
      (e.missing.length > 0 ? ` (${e.missing.join(", ")})` : "") +
      ". Bruk en nyere maskin.",
  }),
  busy: () => ({
    title: "En annen transkribering pågår",
    hint: "Vent til den er ferdig og prøv igjen.",
  }),
  already_downloading: () => ({
    title: "Modellen lastes allerede ned",
    hint: "Vent til den er ferdig.",
  }),
  cancelled: () => ({ title: "Avbrutt", hint: "" }),
  whisper: () => ({
    title: "Transkriberingen stoppet uventet",
    hint: "Prøv igjen. Skjer det igjen, kan du prøve et lavere kvalitetsvalg eller lagre filen på nytt som mp3 eller wav.",
  }),
  file_exists: () => ({
    title: "Filen finnes fra før",
    hint: "Velg et annet navn, eller bekreft at den kan erstattes.",
  }),
  not_a_directory: () => ({
    title: "Fant ikke mappen",
    hint: "Velg en mappe som finnes.",
  }),
  invalid_path: () => ({
    title: "Filen eller mappen kan ikke brukes",
    hint: "Flytt filen til en annen mappe, eller gi den et enklere navn, og prøv igjen.",
  }),
  permission_denied: () => ({
    title: "Appen har ikke tilgang",
    hint: "Velg et annet sted, eller sjekk at du har lov til å bruke filen eller mappen.",
  }),
  io: () => ({
    title: "Filen kunne ikke leses eller lagres",
    hint: "Sjekk at disken eller minnepinnen er koblet til og at du har tilgang. Prøv igjen.",
  }),
  internal: () => something_went_wrong,
};

const months = [
  "januar",
  "februar",
  "mars",
  "april",
  "mai",
  "juni",
  "juli",
  "august",
  "september",
  "oktober",
  "november",
  "desember",
];

/** Tekstene i toppen av eksportert tekst (tas med til Rust i `ExportRequest.labels`). */
const headerLabels: HeaderLabels = {
  file: "Fil",
  date: "Dato",
  malform: "Målform",
  stil: "Stil",
  model: "Modell",
  bokmal: "Bokmål",
  nynorsk: "Nynorsk",
  lydrett: "Lydrett",
  tolket: "Tolket",
  notice: "Teksten er maskintranskribert og må kontrolleres mot lyden.",
};

const nb = {
  app: {
    name: "LLAs verktøykasse",
    shortName: "Verktøykasse",
    menuLabel: "Verktøy",
    skipToContent: "Hopp til innholdet",
    closeWithRunning:
      "Transkriberingen pågår fortsatt. Hvis du avslutter nå, går den tapt.",
    closeWithUnsaved: "Du har tekst som ikke er lagret. Hvis du avslutter nå, går den tapt.",
    closeConfirm: "Avslutt likevel",
    closeCancel: "Bli i appen",
    closeTitle: "Avslutte appen?",
  },

  nav: {
    settings: "Innstillinger",
    about: "Om",
  },

  tools: {
    transkribering: {
      name: "Transkribering",
      description: "Gjør lyd og video om til tekst med tidskoder. Alt skjer på din egen maskin.",
    },
  },

  common: {
    close: "Lukk",
    open: "Åpne",
    cancel: "Avbryt",
    back: "Tilbake",
    remove: "Fjern",
    retry: "Prøv igjen",
    ok: "OK",
    unknownError: something_went_wrong,
    nbsp: " ",
  },

  update: {
    /** Plass til oppdateringsvarselet (steg 4). */
    available: (version: string) => `Det finnes en ny versjon: ${version}.`,
    dismiss: "Skjul",
  },

  transkribering: {
    title: "Transkribering",
    drop: {
      title: "Dra inn lyd- eller videofiler",
      or: "eller",
      choose: "Velg fil",
      chooseMore: "Legg til flere filer",
      dragging: "Slipp filene her",
      formats: "mp3, m4a, wav, flac, ogg, mp4 og mov",
      dialogTitle: "Velg lyd- eller videofiler",
      filterName: "Lyd og video",
      added: (n: number) => (n === 1 ? "1 fil lagt til." : `${n} filer lagt til.`),
      duplicates: "Filen ligger allerede i listen.",
    },

    readyTitle: "Klare til å transkribere",
    readyRemove: (name: string) => `Fjern ${name} fra listen`,

    choices: {
      title: "Valg",
      malform: {
        legend: "Målform",
        bokmål: "Bokmål",
        nynorsk: "Nynorsk",
      },
      stil: {
        legend: "Stil",
        lydrett: "Lydrett",
        tolket: "Tolket",
        explainLydrett: "Lydrett: det som blir sagt, også muntlige former.",
        explainTolket: "Tolket: rettet til skriftlig språk.",
        explainLydrettNynorsk:
          "Lydrett gir det som blir sagt. Snakker personen bokmål, blir noe stående på bokmål.",
      },
      kvalitet: {
        legend: "Kvalitet",
        rask: "Rask",
        anbefalt: "Anbefalt",
        best: "Best",
        hint: {
          rask: "Raskest. Passer eldre maskiner og første utkast.",
          anbefalt: "Passer for de fleste.",
          best: "Mest nøyaktig, men tregest. Trenger en kraftig maskin.",
        },
        lowMemory: (gb: number) =>
          `Best trenger en kraftig maskin med 16 GB minne eller mer. Denne har ${gb} GB. Det kan gå tregt eller stoppe. Velg Anbefalt hvis du er usikker.`,
      },
    },

    start: {
      button: "Start",
      buttonMany: (n: number) => `Start (${n} filer)`,
    },

    model: {
      /** «Denne kombinasjonen trenger en modell på 550 MB. Last ned?» */
      needs: (size: string) => `Denne kombinasjonen trenger en modell på ${size}. Last ned?`,
      name: (name: string) => `Modell: ${name}`,
      download: "Last ned",
      resumeInfo: (done: string) => `${done} er lastet ned fra før. Nedlastingen fortsetter der den slapp.`,
      downloading: "Laster ned modellen …",
      progress: (done: string, total: string) => `${done} av ${total}`,
      cancelDownload: "Avbryt nedlasting",
      downloadCancelled: "Nedlastingen ble avbrutt. Det som er lastet ned, beholdes.",
      downloadFailed: "Nedlastingen mislyktes",
      onlineNote: "Modellen lastes ned fra internett én gang. Lyden din sendes aldri noe sted.",
    },

    system: {
      cpuUnsupportedTitle: "Denne maskinen er for gammel til å transkribere",
      cpuUnsupportedHint: (missing: string[]) =>
        "Prosessoren mangler en funksjon som trengs" +
        (missing.length > 0 ? ` (${missing.join(", ")})` : "") +
        ". Bruk en nyere maskin.",
    },

    queue: {
      title: "Filer",
      status: {
        waiting: "Venter",
        running: "Transkriberer",
        starting: "Starter …",
        done: "Ferdig",
        cancelled: "Avbrutt",
        failed: "Feilet",
      },
      open: (name: string) => `Åpne ${name}`,
      cancel: "Avbryt",
      cancelFile: (name: string) => `Avbryt ${name}`,
      removeFile: (name: string) => `Fjern ${name} fra listen`,
      confirmRemoveTitle: "Fjerne teksten?",
      confirmRemoveBody:
        "Teksten er ikke lagret. Hvis du fjerner den fra listen, går den tapt.",
      confirmRemove: "Fjern likevel",
    },

    progress: {
      percent: (p: number) => `${p} %`,
      etaUnknown: "Beregner tid …",
      etaSeconds: "noen sekunder igjen",
      etaLessThanMinute: "under ett minutt igjen",
      etaMinutes: (m: number) => `ca. ${m} min igjen`,
      etaHours: (h: number, m: number) => (m === 0 ? `ca. ${h} t igjen` : `ca. ${h} t ${m} min igjen`),
      label: "Framdrift",
      verifying: "Sjekker modellen …",
      cancelling: "Avbryter …",
      keepOpen: "Maskinen går ikke i dvale mens dette pågår.",
    },

    file: {
      back: "Tilbake til filene",
      meta: (malform: string, stil: string, kvalitet: string) => `${malform} · ${stil} · ${kvalitet}`,
      liveTitle: "Teksten så langt",
      liveEmpty: "Teksten dukker opp her etter hvert.",
      cancelledTitle: "Transkriberingen ble avbrutt",
      cancelledHint: "Ingenting er lagret. Du kan starte på nytt.",
      failedTitle: "Dette gikk ikke",
      restart: "Start på nytt",
      noSpeechTitle: "Vi fant ingen tale i filen",
      noSpeechHint: "Sjekk at det er riktig fil, og at det er hørbar tale i den.",
    },

    result: {
      title: "Resultat",
      hint: "Klikk på tidskoden for å høre lyden derfra. Klikk i teksten for å rette.",
      segmentTime: (time: string) => `Spill av fra ${time}`,
      segmentText: (time: string) => `Tekst fra ${time}`,
      player: "Lydavspiller",
      playbackFailed:
        "Lyden kan ikke spilles av her, men teksten er klar. Lyden er ikke endret.",
      saveAs: "Lagre som …",
      copyAll: "Kopier alt",
      copied: "Teksten er kopiert.",
      copyFailed: "Kunne ikke kopiere. Marker teksten og kopier med tastaturet.",
      saved: (name: string) => `Lagret som ${name}.`,
      savedLocation: "Ligger i samme mappe som lydfilen.",
      saveFailed: "Kunne ikke lagre",
      edited: "Endringer er ikke lagret.",
      reveal: { mac: "Vis i Finder", windows: "Vis i Utforsker", other: "Vis i filbehandler" },
    },

    save: {
      title: "Lagre som",
      formats: {
        "docx-time": { label: "Word med tidskoder", ext: ".docx", hint: "" },
        "docx-plain": { label: "Word uten tidskoder", ext: ".docx", hint: "" },
        "txt-time": { label: "Tekst med tidskoder", ext: ".txt", hint: "" },
        "txt-plain": { label: "Tekst uten tidskoder", ext: ".txt", hint: "" },
        srt: { label: "Undertekster", ext: ".srt", hint: "Til video" },
        vtt: { label: "Undertekster for nett", ext: ".vtt", hint: "" },
      },
      dialogTitle: "Lagre transkripsjonen",
    },

    mock: {
      banner: "Prøvevisning uten ekte transkribering",
    },
  },

  settings: {
    title: "Innstillinger",
    models: {
      title: "Modeller",
      intro:
        "Modellene gjør lyd om til tekst. De lastes ned første gang du trenger dem, og tar plass på disken.",
      empty: "Ingen modeller er lastet ned ennå.",
      total: (size: string) => `Modellene bruker ${size} på denne maskinen.`,
      delete: "Slett",
      deleteFile: (name: string) => `Slett modellen ${name}`,
      confirmTitle: "Slette modellen?",
      confirmBody: (name: string, size: string) =>
        `${name} tar ${size}. Du kan laste den ned igjen senere.`,
      confirmDelete: "Slett",
      partial: (done: string) => `Ikke ferdig nedlastet (${done})`,
      inOwnFolder: "I din egen modellmappe",
      inAppFolder: "I appens mappe",
      deleteBlocked: "Ligger i din egen mappe. Slett filen der.",
      deleted: (name: string) => `${name} er slettet.`,
      stil: { verbatim: "Lydrett", semantic: "Eldre tolket-modell (brukes ikke)", main: "Tolket" },
      size: { small: "Rask", medium: "Anbefalt", large: "Best" },
      loadFailed: "Kunne ikke hente listen over modeller.",
    },
    folder: {
      title: "Egen modellmappe",
      intro:
        "Bruk dette hvis redaksjonen deler modeller på en nettverksdisk eller en minnepinne. Appen leter først i denne mappen.",
      current: (path: string) => `Valgt mappe: ${path}`,
      none: "Ingen egen mappe er valgt. Appen bruker sin egen mappe.",
      appFolder: (path: string) => `Appens mappe: ${path}`,
      choose: "Velg mappe …",
      reset: "Bruk appens mappe",
      dialogTitle: "Velg mappen med modeller",
      saved: "Modellmappen er lagret.",
      reset_done: "Appens egen mappe brukes igjen.",
    },
    decoding: {
      title: "Nøyaktighet og fart",
      intro: "Gjelder alle transkriberinger.",
      beam5: "Grundig",
      beam5Hint: "Litt bedre tekst, litt tregere.",
      greedy: "Raskere",
      greedyHint: "Omtrent halvannen gang så fort, med litt flere feil.",
      legend: "Nøyaktighet og fart",
    },
    updates: {
      title: "Oppdateringer",
      toggle: "Se etter ny versjon når appen starter",
      hint: "Appen spør bare om det finnes en nyere versjon. Ingen lyd, tekst eller filnavn sendes.",
    },
    loadFailed: "Kunne ikke lagre innstillingen.",
  },

  about: {
    title: "Om verktøykassen",
    version: (v: string) => `Versjon ${v}`,
    versionUnknown: "Versjon ukjent",
    by: "Laget for medlemmene i Landslaget for lokalaviser.",
    privacyTitle: "Personvern",
    privacy: "Lyden din forlater aldri maskinen.",
    privacyDetail:
      "Alt skjer lokalt. Appen kobler seg bare til internett for å laste ned modeller når du ber om det, og for å sjekke om det finnes en ny versjon (dette kan slås av under Innstillinger).",
    licensesTitle: "Lisenser",
    licensesIntro: "Verktøykassen bygger på åpen kildekode og åpne modeller.",
    licenses: [
      {
        name: "NB-Whisper",
        by: "Nasjonalbibliotekets KI-lab",
        license: "Apache License 2.0",
        note: "Språkmodellene som gjør tale om til norsk tekst. Lastes ned når du trenger dem.",
      },
      {
        name: "whisper.cpp",
        by: "Georgi Gerganov og bidragsytere",
        license: "MIT",
        note: "Programmet som kjører modellene på din maskin.",
      },
      {
        name: "Tauri",
        by: "Tauri-prosjektet",
        license: "MIT og Apache 2.0",
        note: "Rammeverket appen er bygget på.",
      },
      {
        name: "Symphonia",
        by: "Philip Deljanov og bidragsytere",
        license: "MPL 2.0",
        note: "Leser lydfilene.",
      },
      {
        name: "Øvrige komponenter",
        by: "",
        license: "MIT, Apache 2.0 og lignende",
        note: "Blant annet rubato (omregning av lyd) og docx-rs (Word-filer).",
      },
    ],
    licenseLine: (by: string, license: string) => (by ? `${by} · ${license}` : license),
  },

  errors,
  headerLabels,

  months,
  /** `18. oktober 2026`. */
  dateLong: (d: Date) => `${d.getDate()}. ${months[d.getMonth()] ?? ""} ${d.getFullYear()}`,

  units: { kb: "kB", mb: "MB", gb: "GB" },
  files: (n: number) => (n === 1 ? "1 fil" : `${n} filer`),
} as const;

export type Texts = typeof nb;
export const t: Texts = nb;
export default nb;
