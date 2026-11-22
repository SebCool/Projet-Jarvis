# Android Pilot — instructions pour Claude Code

Tu pilotes le **Samsung Galaxy S24 Ultra** de Seb via le serveur MCP `android-pilot` (ADB, sans root).
Réponds toujours en **français**, direct, sans enrober. Préférer l'action aux questions.

## À lire en premier
1. `.claude/HANDOFF.md` — état exact du projet et prochaine étape
2. `.claude/ANDROID_PILOT_BRAIN.md` — mémoire projet (pièges, roadmap)
3. `README.md` — architecture et outils

## Règles sur le téléphone
- **READ → COMPARE → PATCH** : lire l'état avant toute modification.
- `snapshot` avant une série de modifications.
- Profils et `battery_app_plan` : **toujours `dry_run=True` d'abord**, montrer le plan, attendre le feu vert.
- Modifications uniquement via les outils journalisés (annulables par `rollback`). `shell_unsafe` = dernier recours,
  expliquer avant ce que ça fait et comment revenir en arrière.
- Ne jamais restreindre **Home Assistant Companion** (présence JARVIS) ni les apps de la liste `keep`.

## Commandes
```powershell
.venv\Scripts\python -m pytest -q          # tests (faux ADB)
adb devices -l                             # téléphone visible ?
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1   # (ré)installation
```

## Fin de session productive
Mettre à jour `CHANGELOG.md`, `.claude/ANDROID_PILOT_BRAIN.md`, `.claude/HANDOFF.md`, puis commit + push.
