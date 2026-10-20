// Alle brukertekster i appen, på bokmål (regel 10). Ingen tekst står i
// komponentene. Nynorsk grensesnitt er ønsket senere (docs/senere.md): da lages
// en `nn.ts` med samme form (`Texts`), og `t` velges ved oppstart.
//
// Skriv som til en travel journalist: korte setninger, ingen fagord.

import type { JvError } from "../tools/jv/api";
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
  hint: "Prøv igjen. Skjer det igjen, start appen på nytt og ta kontakt med Samarbeidsdesken.",
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

type JvErrorTexts = { [K in JvError["code"]]: (e: Extract<JvError, { code: K }>) => ErrorText };

/** «26.6.2» og «15» sies som de står; «15.0» blir «15». */
const osName = (v: string) => `macOS ${v.replace(/(\.0)+$/, "")}`;

const jvErrors: JvErrorTexts = {
  catalog_signature: () => ({
    title: "Verktøylisten kunne ikke kontrolleres",
    hint: "Av sikkerhetshensyn brukes ikke listen. Prøv igjen senere. Hjelper ikke det, ta kontakt med Samarbeidsdesken.",
  }),
  catalog_invalid: () => ({
    title: "Verktøylisten kunne ikke leses",
    hint: "Prøv igjen senere. Hjelper ikke det, ta kontakt med Samarbeidsdesken.",
  }),
  catalog_outdated: () => ({
    title: "Verktøylisten er eldre enn den appen allerede har",
    hint: "Prøv igjen senere. Hjelper ikke det, ta kontakt med Samarbeidsdesken.",
  }),
  catalog_missing: () => ({
    title: "Appen har ingen verktøyliste ennå",
    hint: "Den hentes fra internett. Sjekk at du er på nett og prøv igjen.",
  }),
  catalog_key_missing: () => ({
    title: "Denne versjonen av appen kan ikke laste ned verktøy",
    hint: "Last ned den nyeste versjonen av appen fra lla.no, eller ta kontakt med Samarbeidsdesken.",
  }),
  unknown_tool: () => something_went_wrong,
  not_for_platform: () => ({
    title: "Verktøyet er ikke klart for denne maskinen ennå",
    hint: "Det kommer i en senere versjon.",
  }),
  needs_newer_app: () => ({
    title: "Verktøyet krever en nyere versjon av appen",
    hint: "Se etter ny versjon under Innstillinger, og prøv igjen etterpå.",
  }),
  needs_newer_os: (e) => ({
    title: `Verktøyet trenger ${osName(e.min_os)} eller nyere`,
    hint: "Denne maskinen har en eldre versjon. Oppdater macOS under Systeminnstillinger, Generelt, Programvareoppdatering, og prøv igjen.",
  }),
  not_installed: () => ({
    title: "Verktøyet er ikke lastet ned",
    hint: "Last det ned først.",
  }),
  busy: () => ({
    title: "Verktøyet er opptatt",
    hint: "Vent til jobben er ferdig, og prøv igjen.",
  }),
  checksum_mismatch: () => ({
    title: "Nedlastingen ble skadet",
    hint: "Filen ble ikke lastet ned riktig, og er slettet. Prøv å laste ned på nytt.",
  }),
  unsafe_archive: () => ({
    title: "Nedlastingen så ikke trygg ut",
    hint: "Den er ikke installert. Prøv igjen senere. Skjer det igjen, ta kontakt med Samarbeidsdesken.",
  }),
  archive_read: () => ({
    title: "Nedlastingen kunne ikke pakkes ut",
    hint: "Filen kan være skadet. Prøv å laste ned på nytt.",
  }),
  manifest_invalid: () => ({
    title: "Verktøypakken passer ikke med appen",
    hint: "Prøv å laste ned på nytt. Skjer det igjen, ta kontakt med Samarbeidsdesken.",
  }),
  code_signature: () => ({
    title: "Verktøyet er ikke godkjent av macOS",
    hint: "Av sikkerhetshensyn kjøres det ikke. Fjern verktøyet under Innstillinger og last det ned på nytt.",
  }),
  trial_run_failed: () => ({
    title: "Verktøyet startet ikke",
    hint: "Det ble ikke installert. Prøv å laste ned på nytt. Skjer det igjen, ta kontakt med Samarbeidsdesken.",
  }),
  tool_failed: () => ({
    title: "Verktøyet stoppet uventet",
    hint: "Prøv igjen. Skjer det igjen, sjekk at filen åpner seg i et vanlig program, og ta kontakt med Samarbeidsdesken.",
  }),
  report_invalid: () => ({
    title: "Verktøyet ble ferdig, men svaret kunne ikke leses",
    hint: "Se i mappen om filene ble laget. Prøv ellers på nytt.",
  }),
  invalid_args: () => ({
    title: "Valgene passer ikke",
    hint: "Sjekk filene og valgene, og prøv igjen.",
  }),
  download: (e) => {
    switch (e.cause.code) {
      case "network":
        return {
          title: "Ingen nettforbindelse",
          hint: "Verktøyet lastes ned fra internett. Sjekk at du er på nett og prøv igjen. Det som er lastet ned, beholdes, så nedlastingen fortsetter der den slapp.",
        };
      case "disk_full":
        return {
          title: "Det er ikke nok plass på disken",
          hint: "Frigjør plass og prøv igjen. Modeller og verktøy du ikke bruker, kan fjernes under Innstillinger.",
        };
      case "http_status":
        return {
          title: "Nedlastingen ble avvist",
          hint: "Tjenesten svarte ikke som den skulle. Prøv igjen om litt.",
        };
      case "checksum_mismatch":
      case "size_mismatch":
        return {
          title: "Nedlastingen ble skadet",
          hint: "Filen ble ikke lastet ned riktig, og er slettet. Prøv å laste ned på nytt.",
        };
      case "permission_denied":
        return {
          title: "Appen har ikke tilgang til å lagre verktøyet",
          hint: "Sjekk at du har lov til å skrive til brukermappen din, og prøv igjen.",
        };
      default:
        return {
          title: "Nedlastingen mislyktes",
          hint: "Prøv igjen. Skjer det igjen, ta kontakt med Samarbeidsdesken.",
        };
    }
  },
  cancelled: () => ({ title: "Avbrutt", hint: "" }),
  io: () => ({
    title: "Filen eller mappen kunne ikke leses eller lagres",
    hint: "Sjekk at disken er koblet til og at du har tilgang til mappen. Prøv igjen.",
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
    name: "SD-Verktøy",
    shortName: "Verktøy",
    menuLabel: "Verktøy",
    skipToContent: "Hopp til innholdet",
    closeWithRunning:
      "Noe pågår fortsatt, for eksempel en transkribering, en nedlasting eller en jobb i et verktøy. Hvis du avslutter nå, går det tapt.",
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
    available: (version: string) => `Det finnes en ny versjon: ${version}.`,
    install: "Oppdater nå",
    dismiss: "Senere",
    installing: "Laster ned og installerer. Appen starter på nytt av seg selv.",
    failed: "Oppdateringen mislyktes. Prøv igjen senere, eller last ned den nye versjonen fra nedlastingssiden.",
    busyTitle: "Oppdatere nå?",
    busyBody: "Noe pågår i appen, og appen starter på nytt under oppdateringen. Avbryt oppdateringen og vent til jobben er ferdig, hvis du ikke vil miste arbeid.",
    busyConfirm: "Oppdater likevel",
    busyCancel: "Vent",
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

  jv: {
    common: {
      localNote: "Filene dine behandles bare på denne maskinen.",
      original: "Originalen endres ikke. Resultatet lagres som nye filer.",
    },

    nav: {
      groups: { audio: "Lyd og video", documents: "Dokumenter", language: "Språk" },
      soon: "Kommer",
      notDownloaded: "ikke lastet ned",
      soonLabel: (name: string) => `${name}, kommer`,
      downloadLabel: (name: string) => `${name}, ikke lastet ned`,
    },

    /** Navn, beskrivelse (to–tre linjer) og filtyper for hvert verktøy. */
    tools: {
      compare: {
        name: "Sammenlign versjoner",
        description:
          "Viser hva som er endret mellom to versjoner av et dokument, for eksempel to utkast av et vedtak. Slettet tekst står rødt, ny tekst grønt. Du får en rapport du kan åpne i nettleseren.",
        formats: "txt, md, docx og pdf (pdf med tekst)",
        dropTitle: "Dra inn de to versjonene",
        dialogTitle: "Velg de to versjonene",
        filterName: "Dokumenter",
      },
      metadata: {
        name: "Metadata – vis og fjern",
        description:
          "Viser skjult informasjon i filer, som sted, forfatter og kamera. Du kan også lage en vasket kopi uten den, før du deler filen.",
        formats: "jpg, png, heic, pdf, docx, xlsx og pptx, eller en mappe",
        dropTitle: "Dra inn filer eller en mappe",
        dialogTitle: "Velg filer",
        filterName: "Filer med metadata",
      },
      keyframes: {
        name: "Stillbilder fra video",
        description:
          "Trekker ut bilder fra en video, med tidskode i filnavnet. Du får også et kontaktark med alle bildene. Til å sjekke eller illustrere en sak.",
        formats: "mp4, mov, mkv, m4v, avi og webm",
        dropTitle: "Dra inn videofiler",
        dialogTitle: "Velg videofiler",
        filterName: "Video",
      },
      loudness: {
        name: "Lydnivå",
        description:
          "Setter lydnivået til standard med ett valg, så lyden ikke er for svak eller for sterk. Du får en ny fil. Originalen beholdes.",
        formats: "wav, mp3, m4a, flac, mp4, mov, m4v og mkv",
        dropTitle: "Dra inn lyd- eller videofiler",
        dialogTitle: "Velg lyd- eller videofiler",
        filterName: "Lyd og video",
      },
      subtitles: {
        name: "Teksting",
        description:
          "Gjør en transkripsjon med tidskoder om til undertekster som passer på skjermen. Du får både srt og vtt.",
        formats: "json fra transkriberingen",
        dropTitle: "Dra inn transkripsjonen",
        dialogTitle: "Velg transkripsjonen",
        filterName: "Transkripsjon (json)",
      },
      "pdf-tables": {
        name: "Tabeller fra PDF",
        description:
          "Henter tabeller ut av PDF-er, som budsjetter og regnskap, og legger dem i et regneark. Norske tall som 1 234 567,50 blir ekte tall.",
        formats: "pdf med tekst",
        dropTitle: "Dra inn PDF-filer",
        dialogTitle: "Velg PDF-filer",
        filterName: "PDF",
      },
      ocr: {
        name: "Søkbare PDF-er (OCR)",
        description:
          "Gjør skannede dokumenter søkbare. Sidene leses og får et tekstlag du kan søke i og kopiere fra. Skjeve sider rettes opp.",
        formats: "pdf, jpg, png og tiff, eller en mappe",
        dropTitle: "Dra inn skannede dokumenter",
        dialogTitle: "Velg skannede dokumenter",
        filterName: "Skannede dokumenter",
      },
      redact: {
        name: "Sladding av PDF",
        description:
          "Fjerner fødselsnummer, telefonnumre, e-postadresser og egne ord fra en PDF, slik at teksten faktisk er borte og ikke bare dekket. Du går gjennom treffene før noe sladdes.",
        formats: "pdf med tekst",
        dropTitle: "Dra inn PDF-filen",
        dialogTitle: "Velg PDF-filen",
        filterName: "PDF",
      },
      nynorsk: {
        name: "Bokmål ↔ nynorsk",
        description:
          "Gir et førsteutkast av en tekst på den andre målformen. Ord verktøyet ikke kjenner, merkes, så du ser hva som må sjekkes. Utkastet må alltid leses over.",
        formats: "txt, md og docx",
        dropTitle: "Dra inn tekstfiler",
        dialogTitle: "Velg tekstfiler",
        filterName: "Tekstfiler",
      },
    },

    /** Teksten til valgene i hvert verktøy (skjemaene i `src/tools/<id>/schema.ts`). */
    fields: {
      compare: {
        ignoreWhitespace: {
          label: "Se bort fra mellomrom og linjeskift",
          help: "Slått på: ekstra mellomrom og linjeskift regnes ikke som endringer.",
        },
        ignoreCase: {
          label: "Regn store og små bokstaver som like",
          help: "Slått på: «Kommune» og «kommune» regnes som det samme.",
        },
      },
      metadata: {
        legend: "Hva vil du gjøre?",
        show: { label: "Vis", help: "Viser hva som ligger skjult i filene. Ingenting lagres." },
        clean: {
          label: "Fjern",
          help: "Lager en vasket kopi uten sted, forfatter og annen skjult informasjon. Originalen endres ikke.",
        },
      },
      keyframes: {
        modeLegend: "Hvor ofte",
        every: { label: "Fast intervall", help: "Ett bilde med jevne mellomrom." },
        scenes: { label: "Ved klipp", help: "Ett bilde hver gang bildet klippes." },
        seconds: { legend: "Sekunder mellom bildene", unit: "sekunder", help: "For eksempel 2 gir et bilde annenhver sekund." },
        sensitivityLegend: "Hvor lett det regnes som klipp",
        sensitive: { label: "Lett", help: "Flere bilder. Fanger også myke overganger." },
        normal: { label: "Vanlig", help: "Passer for de fleste videoer." },
        strict: { label: "Strengt", help: "Færre bilder. Bare tydelige klipp." },
      },
      loudness: {
        legend: "Mål",
        podcast: { label: "Podcast", help: "Podcast: −16 LUFS. Passer for nett og mobil." },
        broadcast: { label: "Kringkasting", help: "Kringkasting: −23 LUFS (EBU R128). Passer for radio og TV." },
      },
      subtitles: {
        lengthLegend: "Tegn per linje",
        short: { label: "Kort", help: "Kort: 32 tegn per linje. Passer for små skjermer." },
        normal: { label: "Vanlig", help: "Vanlig: 42 tegn per linje." },
        long: { label: "Lang", help: "Lang: 60 tegn per linje." },
        linesLegend: "Linjer per tekst",
        one: { label: "1 linje", help: "" },
        two: { label: "2 linjer", help: "" },
      },
      "pdf-tables": {
        pages: {
          legend: "Sider",
          placeholder: "Alle sider",
          help: "La stå tomt for alle sider, eller skriv for eksempel 3-7 eller 1,4-5.",
          invalid: "Skriv sidene slik: 3-7 eller 1,4-5.",
        },
        merge: {
          label: "Slå sammen tabeller som fortsetter på neste side",
          help: "Slått på: en tabell over flere sider blir én tabell.",
        },
        csv: { label: "Lag også en csv-fil per tabell", help: "" },
      },
      ocr: {
        text: { label: "Lag også en tekstfil med all teksten", help: "Sider som allerede har tekst, hoppes over." },
      },
      redact: {
        terms: {
          legend: "Egne ord og navn (valgfritt)",
          help: "En tekstfil med ett ord eller navn per linje. Verktøyet søker også etter disse.",
          dialogTitle: "Velg tekstfilen med ord og navn",
          filterName: "Tekstfil",
        },
      },
      nynorsk: {
        legend: "Retning",
        toNynorsk: { label: "Bokmål til nynorsk", help: "Oversetter fra bokmål til nynorsk." },
        toBokmal: { label: "Nynorsk til bokmål", help: "Oversetter fra nynorsk til bokmål." },
      },
    },

    /** Skjermen for et verktøy som ikke er lastet ned. */
    install: {
      accepts: "Tar imot",
      size: "Størrelse",
      version: "Versjon",
      download: "Last ned verktøyet",
      cancel: "Avbryt nedlasting",
      downloading: "Laster ned verktøyet …",
      installing: "Kontrollerer og installerer …",
      progress: (done: string, total: string) => `${done} av ${total}`,
      onlineNote: "Verktøyet lastes ned fra internett én gang.",
      checking: "Sjekker hva som er tilgjengelig …",
      cancelled: "Nedlastingen ble avbrutt. Det som er lastet ned, beholdes.",
      failedTitle: "Nedlastingen mislyktes",
      done: "Verktøyet er lastet ned og klart til bruk.",
      downloaded: (name: string) => `${name}: verktøyet er lastet ned.`,
      comingTitle: (platform: "mac" | "windows" | "other") =>
        platform === "windows" ? "Kommer for Windows" : platform === "mac" ? "Kommer for Mac" : "Kommer",
      comingHint: "Verktøyet er ikke klart for denne maskinen ennå. Det kommer i en senere versjon av appen.",
      needsOsTitle: (min: string) => `Verktøyet trenger macOS ${min.replace(/(\.0)+$/, "")} eller nyere`,
      needsOsHint:
        "Denne maskinen har en eldre versjon. Oppdater macOS under Systeminnstillinger, Generelt, Programvareoppdatering. Da kan du laste ned verktøyet.",
      needsAppTitle: "Verktøyet krever en nyere versjon av appen",
      needsAppHint: "Se etter ny versjon under Innstillinger. Da kan du laste ned verktøyet.",
      catalogFailedTitle: "Kunne ikke hente verktøylisten",
    },

    /** Skjermen for et verktøy som er lastet ned. */
    screen: {
      readyTitle: "Filer",
      chooseFiles: "Velg fil",
      chooseMore: "Legg til flere filer",
      chooseFolder: "Velg mappe",
      or: "eller",
      dragging: "Slipp filene her",
      removeFile: (name: string) => `Fjern ${name} fra listen`,
      swap: "Bytt rekkefølge",
      roles: ["Gammel versjon", "Ny versjon"] as readonly string[],
      folder: "Mappe",
      added: (n: number) => (n === 1 ? "1 fil lagt til." : `${n} filer lagt til.`),
      needExactly: (n: number) =>
        n === 1 ? "Dette verktøyet tar én fil om gangen." : `Dette verktøyet trenger nøyaktig ${n} filer.`,
      unsupportedTitle: "Filformatet støttes ikke",
      unsupportedHint: (names: string[], formats: string) =>
        `${names.length === 1 ? `Filen «${names[0]}»` : `Filene ${names.map((n) => `«${n}»`).join(", ")}`} passer ikke her. Verktøyet leser ${formats}. Gjør filen om til et av disse formatene, og legg den til på nytt.`,
      choicesTitle: "Valg",
      outTitle: "Lagres i",
      outChange: "Velg annen mappe",
      outDialogTitle: "Velg mappen resultatet skal lagres i",
      outNone: "Velg en mappe",
      run: "Kjør",
      runNeedFiles: "Legg til filer først.",
      running: "Jobber …",
      starting: "Starter …",
      cancel: "Avbryt",
      cancelling: "Avbryter …",
      progressLabel: "Framdrift",
      percent: (p: number) => `${p} %`,
      keepOpen: "Ikke lukk appen mens dette pågår.",
      invalidChoices: "Rett opp valgene som er markert, og prøv igjen.",
      pickFile: "Velg fil …",
      removeChosenFile: "Fjern",
    },

    result: {
      doneTitle: "Ferdig",
      doneAnnounce: (name: string) => `${name}: ferdig.`,
      cancelledTitle: "Avbrutt",
      cancelledHint: "Ingenting er lagret. Du kan kjøre på nytt.",
      failedTitle: "Dette gikk ikke",
      warnings: "Dette bør du se på",
      warningLabel: "Advarsel",
      files: "Filer som ble laget",
      noFiles: "Ingen filer ble laget.",
      reveal: { mac: "Vis i Finder", windows: "Vis i Utforsker", other: "Vis i filbehandler" },
      revealFile: (name: string, where: string) => `${where}: ${name}`,
      again: "Kjør på nytt",
      newJob: "Ny jobb",
      draft: "Utkast – må leses over",
      draftHint:
        "Dette er en maskinoversettelse. Les gjennom teksten før den brukes. Ord verktøyet ikke kjente, er markert.",
      details: "Vis feltene",
      fieldsCount: (n: number, sensitive: number) =>
        sensitive > 0 ? `${n} felt, ${sensitive} følsomme` : `${n} felt`,
      sensitive: "Følsom",
      groups: {
        Sted: "Sted",
        Person: "Person",
        Utstyr: "Utstyr",
        Tid: "Tid",
        Annet: "Annet",
      } as Record<string, string>,
    },

    redact: {
      find: "Finn",
      findHint: "Først finner verktøyet treffene. Ingenting sladdes før du har gått gjennom dem.",
      termsLegend: "Egne ord og navn (valgfritt)",
      termsHelp: "En tekstfil med ett ord eller navn per linje. Verktøyet søker også etter disse.",
      stepFind: "1. Finn",
      stepRedact: "2. Sladd",
      reviewTitle: "Gå gjennom treffene",
      reviewHint:
        "Kryss av for det som skal sladdes. Du kan bare krysse av og på. Teksten under det sladdede er borte for godt i den nye filen. Originalen endres ikke.",
      noHits: "Fant ingen treff. Du kan likevel lage en vasket kopi, der metadata, bokmerker og lenker er fjernet.",
      colRedact: "Sladd",
      colType: "Type",
      colPage: "Side",
      colExcerpt: "Utdrag",
      page: (n: number) => `Side ${n}`,
      toggle: (type: string, where: string) => `Sladd ${type}, ${where}`,
      types: {
        fodselsnummer: "Fødselsnummer",
        d_nummer: "D-nummer",
        telefon: "Telefonnummer",
        epost: "E-postadresse",
        term: "Eget ord",
      } as Record<string, string>,
      placements: {
        side: "",
        "utenfor sideflaten": "Utenfor siden",
        "skjult lag": "Skjult lag",
        bokmerke: "Bokmerke",
        lenke: "Lenke",
        sidelabel: "Sidenummer",
        metadata: "Metadata",
      } as Record<string, string>,
      rejectedTitle: "Mulige numre som ble forkastet",
      rejectedHint:
        "Disse ser ut som numre, men sifrene står langt fra hverandre. Det er trolig tall i en tabell, men noen kan være ekte numre. De er ikke krysset av. Kryss av på dem som skal sladdes.",
      rejectedBadge: "Forkastet",
      selected: (n: number, total: number) => `${n} av ${total} valgt for sladding`,
      selectAll: "Kryss av alle",
      selectNone: "Fjern alle avkrysninger",
      redactButton: "Sladd",
      redactNothing: "Lag vasket kopi uten sladding",
      back: "Tilbake til Finn",
      backToReview: "Tilbake til treffene",
      savingPlan: "Lagrer valgene …",
      planFailed: "Kunne ikke lese eller lagre listen over treff",
      found: (n: number, rejected: number) =>
        (n === 0 ? "Fant ingen treff." : n === 1 ? "Fant 1 treff." : `Fant ${n} treff.`) +
        (rejected === 0 ? "" : rejected === 1 ? " 1 mulig nummer ble forkastet." : ` ${rejected} mulige numre ble forkastet.`),
    },

    settings: {
      title: "Verktøy",
      intro:
        "Verktøyene lastes ned når du trenger dem, og tar plass på disken. Ingenting lastes ned eller oppdateres uten at du trykker.",
      empty: "Ingen verktøy er lastet ned ennå.",
      total: (size: string) => `Verktøyene bruker ${size} på denne maskinen.`,
      versionAndSize: (version: string, size: string) => `Versjon ${version} · ${size}`,
      checkUpdates: "Se etter oppdateringer",
      checking: "Sjekker …",
      update: "Oppdater",
      updateFile: (name: string, version: string) => `Oppdater ${name} til versjon ${version}`,
      updateAvailable: (version: string) => `Ny versjon: ${version}`,
      updating: "Oppdaterer …",
      remove: "Fjern",
      removeFile: (name: string) => `Fjern verktøyet ${name}`,
      confirmTitle: "Fjerne verktøyet?",
      confirmBody: (name: string, size: string) => `${name} tar ${size}. Du kan laste det ned igjen senere.`,
      confirmRemove: "Fjern",
      removed: (name: string) => `${name} er fjernet.`,
      upToDate: "Alle verktøyene er oppdatert.",
      foundUpdates: (n: number) => (n === 1 ? "Det finnes en ny versjon av 1 verktøy." : `Det finnes nye versjoner av ${n} verktøy.`),
      checkFailed: "Kunne ikke sjekke. Er maskinen på nett? Siste kjente liste vises.",
      busy: "Verktøyet brukes akkurat nå. Vent til jobben er ferdig.",
      loadFailed: "Kunne ikke hente listen over verktøy.",
      onlineNote: "Dette sjekker bare når du trykker. Ingen filer eller navn sendes.",
    },

    about: {
      title: "Verktøy du har lastet ned",
      none: "Ingen ennå.",
      line: (version: string, license: string) => `Versjon ${version} · ${license}`,
      note: "Hvert verktøy har med lisensene for programmene det bygger på.",
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
      greedyHint: "Raskere for tolket, men litt mindre nøyaktig. Lydrett bruker alltid grundig.",
      legend: "Nøyaktighet og fart",
    },
    updates: {
      title: "Oppdateringer",
      toggle: "Se etter ny versjon når appen starter",
      hint: "Appen spør bare om det finnes en nyere versjon. Ingen lyd, tekst eller filnavn sendes.",
      checkNow: "Se etter ny versjon nå",
      checking: "Sjekker …",
      upToDate: "Du har den nyeste versjonen.",
      foundNew: (v: string) => `Ny versjon funnet: ${v}. Se øverst i vinduet.`,
      checkFailed: "Kunne ikke sjekke. Er maskinen på nett?",
      checkNowHint: "Dette sjekker bare når du trykker, også når den automatiske sjekken er av.",
    },
    loadFailed: "Kunne ikke lagre innstillingen.",
  },

  about: {
    title: "Samarbeidsdeskens verktøykasse",
    version: (v: string) => `Versjon ${v}`,
    versionUnknown: "Versjon ukjent",
    by: "Laget av John Inge Johansen og Claude Code for medlemmer i Samarbeidsdesken.",
    privacyTitle: "Personvern",
    privacy: "Programmene kan kjøres uten internettilgang, og sender ikke fra seg noe informasjon.",
    privacyDetail:
      "Når du laster ned pakker eller sjekker for oppdateringer, må du ha nett. Sjekken ved oppstart kan slås av under Innstillinger.",
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
    fullLicenses: {
      summary: "Vis full lisenstekst",
      intro: "Hele lisensteksten for NB-Whisper, whisper.cpp, Tauri, Symphonia og alle andre komponenter som følger med appen.",
      loading: "Henter lisensteksten …",
      failed: "Kunne ikke vise lisensteksten.",
      regionLabel: "Full lisenstekst",
    },
    licenseLine: (by: string, license: string) => (by ? `${by} · ${license}` : license),
  },

  errors,
  jvErrors,
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
