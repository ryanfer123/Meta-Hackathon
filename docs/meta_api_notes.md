# Meta API findings - 2026-10-27

Documentation verified; live observations pending. User will supply keys later. No account, billing, regional access, spend notification or paid endpoint has been tested.

- Base URL https://api.meta.ai/v1; Spark `muse-spark-1.3` via OpenAI-compatible requests. Image count limits require a live spike.
- SAM `sam-3.1` uses Responses with image/video inputs, not a guessed `/segment` endpoint. Output is special-token text, not JSON masks. Use the official parser. Stable IDs hold within a video response; missing frames/occlusion require care. Keyframe image calls cannot guarantee identity of identical objects.
- Voice uses multipart `/asr/transcribe`, fields `request` and `audio`. Mono PCM16 WAV at 16/24 kHz; ENDPOINTING yields turns with startMs/endMs, not word timestamps.
- Glimmer `meta-models/Muse-Glimmer-30B`: BF16 needs about 72 GB serving VRAM. Modal script targets A100-80GB. Vision and latency unverified.
- Baseten hackathon model ID in supplied guide: `meta-models/muse-spark-open-1026`; not live verified.
- Costs must be measured from actual usage; estimates are not bills. Spike records latency/usage when explicitly run. No live numbers are published yet.

Sources: [Overview](https://dev.meta.ai/docs), [SAM](https://dev.meta.ai/docs/sam/overview), [SAM grammar](https://dev.meta.ai/docs/sam/reading-segmentation), [parser](https://dev.meta.ai/docs/sam/client-libraries), [Voice](https://dev.meta.ai/docs/speech-to-text), [Glimmer](https://dev.meta.ai/docs/muse-glimmer/deploy), [pricing](https://dev.meta.ai/docs/pricing-rate-limits).
