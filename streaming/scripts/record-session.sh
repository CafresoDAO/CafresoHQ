#!/bin/bash
# ── CafresoAI Session Recorder ──────────────────────────────────────────
# Captures a remote desktop stream to MP4 using ffmpeg.
#
# Environment variables:
#   SESSION_ID        - Session identifier (required)
#   STREAM_URL        - RTSP/RTP/HTTP URL to capture (required)
#   DISPLAY_URL       - Alternative: X11 display capture URL
#   RECORDING_DURATION - Max duration in seconds (0 = unlimited)
#   VIDEO_CODEC       - Output codec (default: libx264)
#   VIDEO_QUALITY     - CRF quality (default: 23, lower = better)
#   RESOLUTION        - Output resolution (default: 1920x1080)
#   FRAMERATE         - Output framerate (default: 30)

set -euo pipefail

SESSION_ID="${SESSION_ID:-unknown}"
STREAM_URL="${STREAM_URL:-}"
DISPLAY_URL="${DISPLAY_URL:-}"
RECORDING_DURATION="${RECORDING_DURATION:-0}"
VIDEO_CODEC="${VIDEO_CODEC:-libx264}"
VIDEO_QUALITY="${VIDEO_QUALITY:-23}"
RESOLUTION="${RESOLUTION:-1920x1080}"
FRAMERATE="${FRAMERATE:-30}"

# Create output directory
OUTPUT_DIR="/recordings/${SESSION_ID}"
mkdir -p "${OUTPUT_DIR}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/${TIMESTAMP}.mp4"

echo "[recorder] Session: ${SESSION_ID}"
echo "[recorder] Output:  ${OUTPUT_FILE}"
echo "[recorder] Codec:   ${VIDEO_CODEC} (crf=${VIDEO_QUALITY})"
echo "[recorder] Resolution: ${RESOLUTION} @ ${FRAMERATE}fps"

# Determine input source
INPUT_URL="${STREAM_URL:-${DISPLAY_URL}}"
if [ -z "${INPUT_URL}" ]; then
    echo "[recorder] ERROR: No STREAM_URL or DISPLAY_URL provided"
    exit 1
fi

echo "[recorder] Source:  ${INPUT_URL}"

# Wait for stream to be available (up to 60s)
echo "[recorder] Waiting for stream..."
for i in $(seq 1 60); do
    if ffprobe -v quiet -timeout 2000000 "${INPUT_URL}" 2>/dev/null; then
        echo "[recorder] Stream available after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "[recorder] ERROR: Stream not available after 60s"
        exit 1
    fi
    sleep 1
done

# Build ffmpeg command
FFMPEG_ARGS=(
    -hide_banner
    -loglevel warning
    -stats
    -i "${INPUT_URL}"
    -c:v "${VIDEO_CODEC}"
    -crf "${VIDEO_QUALITY}"
    -preset fast
    -s "${RESOLUTION}"
    -r "${FRAMERATE}"
    -c:a aac
    -b:a 128k
    -movflags +faststart
)

# Add duration limit if set
if [ "${RECORDING_DURATION}" != "0" ]; then
    FFMPEG_ARGS+=(-t "${RECORDING_DURATION}")
fi

FFMPEG_ARGS+=("${OUTPUT_FILE}")

echo "[recorder] Starting capture..."

# Handle SIGTERM gracefully (docker stop)
trap 'echo "[recorder] Stopping..."; kill -INT $FFMPEG_PID 2>/dev/null; wait $FFMPEG_PID 2>/dev/null' TERM INT

ffmpeg "${FFMPEG_ARGS[@]}" &
FFMPEG_PID=$!
wait $FFMPEG_PID
EXIT_CODE=$?

if [ -f "${OUTPUT_FILE}" ]; then
    SIZE=$(du -h "${OUTPUT_FILE}" | cut -f1)
    echo "[recorder] Recording saved: ${OUTPUT_FILE} (${SIZE})"
else
    echo "[recorder] WARNING: No output file created (exit code ${EXIT_CODE})"
fi

echo "[recorder] Done."
