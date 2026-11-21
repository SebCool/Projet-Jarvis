# Changelog — Android Pilot

## 0.1.0 — 2026-11-21
- Serveur MCP (SDK v2, compatible v1) : 29 outils (diagnostic, apps, réglages, profils, UI, historique).
- Garde-fous : packages/réglages protégés, shell lecture seule en liste blanche.
- Journal d'annulation (`rollback`, `rollback_all`) + snapshots JSON.
- Profils : `s24u_debloat`, `s24u_perf`, `s24u_battery`.
- 25 tests unitaires (faux ADB). Non encore testé sur le vrai téléphone.
