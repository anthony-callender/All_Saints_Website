#!/usr/bin/env bash
# Transcribe one service that has no YouTube captions (legacy AllSaints_Agent method: yt-dlp + Whisper base),
# limited to the first 75 minutes (enough to contain the sermon and the Creed after it).
# Output: tmp/sermon-worker/transcripts/<video_id>.json, which the worker's FileTranscriptProvider picks up.
#
#   [WHISPER_MODEL=tiny] bash scripts/transcribe_service.sh VIDEO_ID [MINUTES]
set -euo pipefail
vid="${1:?video id}"; minutes="${2:-75}"; model="${WHISPER_MODEL:-base}"
cd "$(dirname "$0")/.."
out=tmp/sermon-worker/transcripts; work=tmp/whisper-$vid
mkdir -p "$out" "$work"
trap 'rm -rf "$work"' EXIT
[ -f "$out/$vid.json" ] && { echo "already transcribed: $vid"; exit 0; }
yt-dlp -q --no-warnings -f bestaudio -o "$work/full.%(ext)s" -- "https://www.youtube.com/watch?v=$vid"
ffmpeg -loglevel error -y -t $((minutes * 60)) -i "$work"/full.* -ac 1 -ar 16000 "$work/$vid.wav"
rm -f "$work"/full.*
PYTHONIOENCODING=utf-8 whisper "$work/$vid.wav" --model "$model" --language English --output_format json \
  --fp16 False --verbose False --output_dir "$work" >/dev/null 2>&1
mv "$work/$vid.json" "$out/$vid.json"
echo "transcribed $vid ($minutes min) -> $out/$vid.json"
