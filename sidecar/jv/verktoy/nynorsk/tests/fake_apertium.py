"""Tiny stand-ins for the Apertium programs, used by the tests.

The tool runs a mode as a pipeline of programs (core.read_mode). The test
fixture writes a one-stage mode file, ``lt-proc $1 -b '<pair>/<mode>.autobil.bin' $2``,
and starts this script as each program: ``fake_apertium.py <program> <args…>``.
``apertium-destxt`` and ``apertium-retxt`` pass the text through unchanged;
``lt-proc`` translates.

The translation mimics the output format of the real pipeline: unknown words are
prefixed with ``*``, a generation error with ``#`` before the lemma (or
inside the word, ``på#drage``), and a word missing from the bilingual
dictionary with ``@``. Like the real program, ``-u`` removes only ``*``;
``#`` and ``@`` stay. It may drop the final newline. Behaviour is steered by env vars:

FAKE_APERTIUM_LOG             append the argument list of each translation (JSON) to this file
FAKE_APERTIUM_FAIL=1          crash with exit code 3
FAKE_APERTIUM_JOIN_LINES=1    turn newlines into spaces (breaks structure)
FAKE_APERTIUM_SPLIT_WORD=<w>      put a line break after this word in the output (breaks structure)
FAKE_APERTIUM_MOVE_SYMBOLS=1  duplicate every *, # and @ in the input with a space
                              (the real transfer rules do this after some words)
"""

import json
import os
import re
import sys

NB_NN = {
    "holder": "held",
    "åpent": "ope",
    "fra": "frå",
    "måned": "månad",
    "betyr": "tyder",
    "flere": "fleire",
    "komme": "kome",
    "skole": "skule",
    "forteller": "fortel",
    "de": "dei",
    "ønsker": "ønskjer",
    "en": "ein",
    "et": "eit",
    "gjøre": "gjere",
    "lettere": "lettare",
    "barn": "born",
    "liker": "likar",
    "høsten": "hausten",
    "oppdiktet": "oppdikta",
    "åpningstider": "opningstider",
    "tilbud": "tilbod",
}
NN_NB = {v: k for k, v in NB_NN.items()}
UNKNOWN = {"fjordglimring", "knaskelure", "fiktivhavn", "xqztvik"}
GENERATION = {"lånerne": "lånarane", "lånarane": "lånerne", "svibrent": "svibrent"}
INNER_GENERATION = {"pådrage": "på#drage"}
UNTRANSLATED = {"friluftsliv"}


def translate_word(word: str, table: dict, unmarked: bool) -> str:
    low = word.lower()
    mark = ""
    if low in UNKNOWN:
        mark, out = "*", word
    elif low in INNER_GENERATION:
        return INNER_GENERATION[low]
    elif low in GENERATION:
        mark, out = "#", GENERATION[low]
    elif low in UNTRANSLATED:
        mark, out = "@", word
    else:
        out = table.get(low, low)
    if word[:1].isupper():
        out = out[:1].upper() + out[1:]
    if mark == "*" and unmarked:
        return out
    return mark + out


def main(argv: list[str]) -> int:
    program, args = argv[0], argv[1:]
    data = sys.stdin.buffer.read()
    if program in ("apertium-destxt", "apertium-retxt"):
        sys.stdout.buffer.write(data)
        return 0
    if program != "lt-proc":
        sys.stderr.write(f"fake: unexpected program {program}\n")
        return 1
    log = os.environ.get("FAKE_APERTIUM_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(args) + "\n")
    unmarked = "-u" in args
    files = [a for a in args if not a.startswith("-")]
    if os.environ.get("FAKE_APERTIUM_FAIL") == "1":
        sys.stderr.write("Segmentation fault (core dumped)\n")
        return 3
    if len(files) != 1 or not os.path.isfile(files[0]):
        sys.stderr.write(f"Error: Cannot open file '{files}' for reading.\n")
        return 1
    table = NB_NN if "nob-nno" in files[0] else NN_NB
    text = data.decode("utf-8")
    if os.environ.get("FAKE_APERTIUM_MOVE_SYMBOLS") == "1":
        text = re.sub(r"([*#@]+)", r"\1 \1", text)
    out = re.sub(r"\w+", lambda m: translate_word(m.group(0), table, unmarked), text)
    split_word = os.environ.get("FAKE_APERTIUM_SPLIT_WORD")
    if split_word:
        out = out.replace(split_word, split_word + "\n.")
    if os.environ.get("FAKE_APERTIUM_JOIN_LINES") == "1":
        out = out.replace("\n", " ")
    sys.stdout.buffer.write(out.rstrip("\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
