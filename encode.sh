#!/usr/bin/env bash
# Stitch a rendered frame sequence into the finished film:
#   title card (2.5 s) -> shot 1 -> shot 2 -> ..., crossfaded, fade to black.
# Usage: encode.sh <frames dir with f_0001.png ...> <output.mp4> [font.ttf]
# Env:   SHOTS     comma-separated shot lengths in frames   (default 96,96,72 = Kingsbridge Central)
#        TITLE     title card text                           (default KINGSBRIDGE CENTRAL)
#        SUBTITLE  line under the title                      (default a station built entirely by code)
set -euo pipefail
FR=${1:-frames}; OUT=${2:-station_film.mp4}
F=${3:-}
SHOTS=${SHOTS:-96,96,72}
TITLE=${TITLE:-KINGSBRIDGE CENTRAL}
SUBTITLE=${SUBTITLE:-a station built entirely by code}
for cand in "$F" /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf "C:/Windows/Fonts/arialbd.ttf"; do
  [ -n "$cand" ] && [ -f "$cand" ] && { F=$cand; break; }
done
IFS=',' read -r -a LENS <<< "$SHOTS"
total=0; for n in "${LENS[@]}"; do total=$((total + n)); done
n=$(ls "$FR"/f_*.png | wc -l); echo "frames: $n (shots ${SHOTS} = $total)"
[ "$n" -eq "$total" ] || { echo "frame count does not match SHOTS"; exit 1; }
sz=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$FR/f_0001.png")
echo "size: $sz  font: $F"
FE=$(printf '%s' "$F" | sed 's/\\/\\\\/g; s/:/\\:/g')   # drawtext wants ':' and '\' escaped

# one trimmed stream per shot
graph=""; start=0; i=0
for n in "${LENS[@]}"; do
  graph+="[0:v]trim=start_frame=${start}:end_frame=$((start + n)),setpts=PTS-STARTPTS,format=yuv420p[s${i}];"
  start=$((start + n)); i=$((i + 1))
done
graph+="color=black:s=${sz}:d=2.5:r=24,format=yuv420p,"
graph+="drawtext=fontfile='${FE}':text='${TITLE}':fontcolor=white:fontsize=h/14:x=(w-text_w)/2:y=(h-text_h)/2-h/18,"
graph+="drawtext=fontfile='${FE}':text='${SUBTITLE}':fontcolor=0xC8B48C:fontsize=h/34:x=(w-text_w)/2:y=(h-text_h)/2+h/22,"
graph+="fade=t=in:st=0:d=0.6,fade=t=out:st=1.9:d=0.6[c0];"

# chain of crossfades: 0.5 s out of the title, 0.6 s between shots
len_s=2.5; prev=c0; i=0
for n in "${LENS[@]}"; do
  d=$([ "$i" -eq 0 ] && echo 0.5 || echo 0.6)
  off=$(awk -v l="$len_s" -v d="$d" 'BEGIN{printf "%.4f", l-d}')
  graph+="[${prev}][s${i}]xfade=transition=fade:duration=${d}:offset=${off}[c$((i + 1))];"
  len_s=$(awk -v l="$len_s" -v n="$n" -v d="$d" 'BEGIN{printf "%.4f", l+n/24-d}')
  prev=c$((i + 1)); i=$((i + 1))
done
fo=$(awk -v l="$len_s" 'BEGIN{printf "%.4f", l-0.7}')
graph+="[${prev}]fade=t=out:st=${fo}:d=0.7,format=yuv420p[v]"

ffmpeg -y -loglevel error -framerate 24 -i "$FR/f_%04d.png" -filter_complex "$graph" \
  -map "[v]" -c:v libx264 -crf 17 -movflags +faststart "$OUT"
ffprobe -v error -show_entries format=duration:stream=width,height,nb_frames -of csv=p=0 "$OUT"
