# Changelog — Android Pilot

## 0.2.0 — 2026-11-22
- Batterie par app : profil `s24u_battery_apps` (liste `keep` + ~30 apps gourmandes, risque low/medium).
- Outil `battery_app_plan` : plan dynamique depuis `dumpsys batterystats` (part arrière-plan, exclusion services premier plan).
- Outils `set_standby_bucket`, `set_doze_exempt` (journalisés) ; `battery_report` renvoie des données structurées.
- Parseur batterystats Android ≤11 et ≥12 (fg/bg/fgs). 32 tests. Toujours pas validé sur le vrai téléphone.

## 0.1.0 — 2026-11-21
- Serveur MCP (SDK v2, compatible v1) : 29 outils (diagnostic, apps, réglages, profils, UI, historique).
- Garde-fous : packages/réglages protégés, shell lecture seule en liste blanche.
- Journal d'annulation (`rollback`, `rollback_all`) + snapshots JSON.
- Profils : `s24u_debloat`, `s24u_perf`, `s24u_battery`.
- 25 tests unitaires (faux ADB). Non encore testé sur le vrai téléphone.
