# MLB Pitch Dashboard data

This orphan branch is a machine-managed persistence layer for normalized MLB game and pitcher-appearance snapshots, plus lightweight read models such as upcoming games and pitching depth/40-man roster status.

- Source code and tests live on `main`.
- GitHub Pages build output is deployed as an Actions artifact, not committed here.
- The refresh workflow validates every snapshot before committing it.
- This branch is never merged into `main`.

See `docs/data-contract.md` on `main` for the schema and failure behavior.
