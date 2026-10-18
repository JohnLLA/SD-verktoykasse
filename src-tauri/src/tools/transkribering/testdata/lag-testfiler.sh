#!/bin/sh
# Lager de korte testfilene for dekodingstestene i decode.rs (kjøres på en Mac).
# Kilde: 1,5 s, 44,1 kHz stereo: tone 440 Hz i 0-0,9 s, stille, ett klikk ved
# nøyaktig 1,000 s, så stille. Klikket brukes til å sjekke tidsforskyvning.
#
# Verktøy (bare for å LAGE testfilene, ikke en del av appen):
#   afconvert (macOS), lame, swift (AVFoundation) og ffmpeg for de tre formatene
#   macOS ikke kan skrive (ogg/Vorbis, ogg/Opus, webm). Appen bruker ikke ffmpeg.
set -eu
cd "$(dirname "$0")"
python3 -I - <<'PY'
import math, struct, wave
r = 44100
w = wave.open("tone-kilde.wav", "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(r)
fr = bytearray()
for i in range(int(1.5 * r)):
    t = i / r
    v = 0.3 * math.sin(2 * math.pi * 440 * t) if t < 0.9 else 0.0
    if i == r:  # 1,000 s
        v = 0.9
    s = int(v * 32767)
    fr += struct.pack("<hh", s, s)
w.writeframes(bytes(fr)); w.close()
PY
afconvert -f m4af -d aac -b 64000 tone-kilde.wav tone.m4a
afconvert -f m4af -d alac tone-kilde.wav tone-alac.m4a
afconvert -f flac -d flac tone-kilde.wav tone.flac
afconvert -f caff -d LEI16@8000 -c 1 tone-kilde.wav tone.caf
afconvert -f AIFF -d BEI16@8000 -c 1 tone-kilde.wav tone.aiff
lame --quiet -b 64 tone-kilde.wav tone.mp3
swift lag-video.swift tone-kilde.wav tone-video.mov
swift lag-video.swift tone-kilde.wav tone-video.mp4
ffmpeg -loglevel error -y -i tone-kilde.wav -c:a vorbis -strict -2 -ac 2 tone.ogg
ffmpeg -loglevel error -y -i tone-kilde.wav -c:a libopus -b:a 32k tone-opus.ogg
ffmpeg -loglevel error -y -i tone-kilde.wav -c:a libopus -b:a 32k tone.webm
rm tone-kilde.wav
ls -l
