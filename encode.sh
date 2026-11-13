#!/usr/bin/env bash
# Stitch the rendered frame sequence into the finished film:
#   title card (2.5 s) -> shot A (96 f) -> shot B (96 f) -> shot C (72 f), crossfaded, fade to black.
# Usage: encode.sh <frames dir with f_0001.png ...> <output.mp4> [font.ttf]
set -euo pipefail
FR=${1:-frames}; OUT=${2:-station_film.mp4}
F=${3:-}
for cand in "$F" /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf "C:/Windows/Fonts/arialbd.ttf"; do
  [ -n "$cand" ] && [ -f "$cand" ] && { F=$cand; break; }
done
n=$(ls "$FR"/f_*.png | wc -l); echo "frames: $n"
sz=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$FR/f_0001.png")
echo "size: $sz  font: $F"
# ffmpeg wants ':' and '\' escaped inside drawtext options
FE=$(printf '%s' "$F" | sed 's/\\/\\\\/g; s/:/\\:/g')
ffmpeg -y -loglevel error -framerate 24 -i "$FR/f_%04d.png" -filter_complex "
[0:v]trim=start_frame=0:end_frame=96,setpts=PTS-STARTPTS,format=yuv420p[a];
[0:v]trim=start_frame=96:end_frame=192,setpts=PTS-STARTPTS,format=yuv420p[b];
[0:v]trim=start_frame=192:end_frame=264,setpts=PTS-STARTPTS,format=yuv420p[c];
color=black:s=${sz}:d=2.5:r=24,format=yuv420p,
drawtext=fontfile='${FE}':text='KINGSBRIDGE CENTRAL':fontcolor=white:fontsize=h/14:x=(w-text_w)/2:y=(h-text_h)/2-h/18,
drawtext=fontfile='${FE}':text='a station built entirely by code':fontcolor=0xC8B48C:fontsize=h/34:x=(w-text_w)/2:y=(h-text_h)/2+h/22,
fade=t=in:st=0:d=0.6,fade=t=out:st=1.9:d=0.6[t];
[t][a]xfade=transition=fade:duration=0.5:offset=2.0[ta];
[ta][b]xfade=transition=fade:duration=0.6:offset=5.4[tab];
[tab][c]xfade=transition=fade:duration=0.6:offset=8.8[v0];
[v0]fade=t=out:st=11.1:d=0.7,format=yuv420p[v]" \
  -map "[v]" -c:v libx264 -crf 17 -movflags +faststart "$OUT"
ffprobe -v error -show_entries format=duration:stream=width,height,nb_frames -of csv=p=0 "$OUT"
