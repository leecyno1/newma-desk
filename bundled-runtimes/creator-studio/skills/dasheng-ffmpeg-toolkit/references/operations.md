# FFmpeg operation defaults

- `probe`: JSON stream and format metadata through `ffprobe`.
- `clip`: accurate H.264/AAC re-encode with `-ss` after input decoding.
- `transcode`: H.264 CRF 18, medium preset, AAC 192k, `yuv420p`, faststart.
- `extract-audio`: PCM 16-bit for `.wav`; MP3 or AAC chosen from the output extension.
- `watermark`: image overlay at bottom right with a 32-pixel margin; audio copied.

All mutating operations reject forbidden repository output roots and existing outputs unless `--overwrite` is supplied.
