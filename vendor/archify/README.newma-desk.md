# Archify in Newma-Desk

This directory contains the architecture renderer subset of
[tt-a1i/archify](https://github.com/tt-a1i/archify), version 2.12.0.

Newma-Desk uses it as a deterministic renderer for validated Mod graph artifacts.
The upstream project and this vendored subset are distributed under the MIT
License; see `LICENSE` in this directory.

The adapter lives in
`services/api/vibe_visualization_api/artifacts/archify.py`. Mod code sends the
Newma-Desk graph artifact contract rather than depending on Archify's internal
file layout. This keeps stored artifacts portable if the renderer changes.
