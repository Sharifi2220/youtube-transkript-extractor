# Third-party dependencies (not bundled)

This repository contains its own source code and small synthetic test fixtures. It does not bundle YouTube media, machine learning models, `deno.exe`, NVIDIA drivers, CUDA, FFmpeg or third-party Python wheels.

- [yt-dlp](https://github.com/yt-dlp/yt-dlp): Python package (Unlicense for PyPI source/wheel; different distribution formats may contain additional licenses). See upstream licensing notes.
- [yt-dlp-ejs](https://github.com/yt-dlp/ejs): companion JavaScript component, including Unlicense/MIT/ISC-licensed portions.
- [Deno](https://github.com/denoland/deno): optional external JavaScript runtime. See upstream distribution license.
- [openai-whisper](https://github.com/openai/whisper): optional local ASR engine. See upstream license.
- [PyTorch](https://github.com/pytorch/pytorch): optional ASR execution backend. See upstream license.
- [FFmpeg](https://ffmpeg.org/legal.html): media decoder used by Whisper if separately installed; licensing depends on the selected build.

Users who install or redistribute dependencies must comply with their respective license notices. The MIT license in this repository covers only this project's own code; it does **not** relicense third-party software, models, YouTube captions, or videos. In particular, do not redistribute a compiled single-file executable with these dependencies before separately reviewing the licenses of the exact binaries and included modules.
