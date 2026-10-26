# Contributing

Thank you for helping improve YouTube Transkript Extractor.

- Keep the app small, local-first and free of account/registration requirements.
- Changes should focus on existing captions and explicitly selected local media; don't add automatic YouTube audio/video downloading, account scraping or access restriction bypassing.
- Include synthetic unit tests for parsing, exports, data-loss prevention and error handling. Avoid committing copyrighted third-party captions or personal media.
- Before a pull request run `python -m unittest discover -s tests -v` and `python -m compileall -q app.py transcript_core.py local_asr.py tests`.
- Document whether features were tested using mocks, actual desktop operation or real accessible sources.
- Use small pull requests and don't change dependencies or run installers in someone else's environment without consent.
