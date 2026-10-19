"""A tiny stand-in for the ``apertium`` command, used by the tests.

It mimics the output format of the real program: unknown words are
prefixed with ``*``, a generation error with ``#`` before the lemma (or
inside the word, ``på#drage``), and a word missing from the bilingual
dictionary with ``@``. Like the real program, ``-u`` removes only ``*``;
``#`` and ``@`` stay. It may drop the final newline. Behaviour is steered by env vars:

FAKE_APERTIUM_LOG             append the argument list (JSON) to this file
FAKE_APERTIUM_MODES           installed modes (default "nob-nno nno-nob")
FAKE_APERTIUM_NO_LIST=1       "-l" is not supported (exit 1)
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
    log = os.environ.get("FAKE_APERTIUM_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(argv) + "\n")
    modes = os.environ.get("FAKE_APERTIUM_MODES", "nob-nno nno-nob").split()
    unmarked = False
    mode = None
    args = iter(argv)
    for arg in args:
        if arg == "-l":
            if os.environ.get("FAKE_APERTIUM_NO_LIST") == "1":
                sys.stderr.write("apertium: invalid option -- 'l'\n")
                return 1
            sys.stdout.write("\n".join(modes) + "\n")
            return 0
        if arg == "-u":
            unmarked = True
        elif arg == "-f":
            fmt = next(args)
            if fmt != "txt":
                sys.stderr.write(f"Error: Unknown format {fmt}\n")
                return 1
        elif arg.startswith("-"):
            sys.stderr.write(f"Error: unsupported option {arg}\n")
            return 1
        else:
            mode = arg
    if os.environ.get("FAKE_APERTIUM_FAIL") == "1":
        sys.stderr.write("Segmentation fault (core dumped)\n")
        return 3
    if mode not in modes:
        sys.stderr.write(f"Error: Mode {mode} does not exist.\n")
        return 1
    table = NB_NN if mode == "nob-nno" else NN_NB
    text = sys.stdin.buffer.read().decode("utf-8")
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
