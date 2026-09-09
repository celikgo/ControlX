`ci.yml` runs lint, format check, strict types on `core/`, and the test suite on Linux and
macOS. The `golden-path` job proves the offline audit → patch → re-audit loop from a clean
checkout using only the shipped example packs, with no API keys.
