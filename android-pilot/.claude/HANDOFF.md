# HANDOFF — Android Pilot (cloud → Claude Code local)

> Passation du 2026-11-22. Source : session cloud Claude Code (branche `ccr-355f178b-z54gah` de `SebCool/Projet-Jarvis`).
> Objectif de la session locale : **première connexion au vrai téléphone et validation sur device**.

## 1. Instructions pour le prochain Claude
- **Rôle** : pilote du Samsung Galaxy S24 Ultra de Seb via le serveur MCP `android-pilot` (ADB, sans root).
- **Langue** : français. Direct, sans enrobage. Questions seulement si une info critique manque.
- **Méthode** : READ → COMPARE → PATCH. `snapshot` avant toute série de modifs. `dry_run=True` avant tout profil/plan.
- **Interdits** : restreindre HA Companion ; toucher aux packages/réglages protégés (`guard.py`) ; `shell_unsafe` sans
  expliquer avant l'effet et le retour arrière.
- **Fin de session** : MAJ `CHANGELOG.md`, `ANDROID_PILOT_BRAIN.md`, ce fichier, commit + push.

## 2. État technique
| Élément | Valeur |
|---|---|
| Version | 0.2.0 |
| Emplacement local | `D:\AndroidPilot\Projet-Jarvis\android-pilot\` (clone sparse, seul ce dossier est extrait) |
| Repo / branche | `https://github.com/SebCool/Projet-Jarvis` — `ccr-355f178b-z54gah` |
| Stack | Python ≥ 3.10, `mcp` (v2 `MCPServer`, fallback v1 `FastMCP`), pyyaml, pillow |
| Tests | `.venv\Scripts\python -m pytest -q` → **32 passés** (faux ADB) |
| MCP Claude Code | `.mcp.json` généré par `scripts\setup_windows.ps1` (chemins absolus, non versionné) |
| Journal des modifs | `%USERPROFILE%\.android-pilot\journal.jsonl` ; snapshots : `...\snapshots\` |
| Outils MCP | 32 (diagnostic, apps, réglages, batterie par app, profils, UI, historique, shell) |

## 3. Travail validé (en cloud, sans téléphone)
- Serveur MCP démarre en stdio, expose 32 outils, messages de refus remontés à Claude (wrapper `_Tools`).
- Garde-fous : packages protégés (SystemUI, téléphonie, IMS, Knox, GMS, launcher, clavier, GOS…), réglages
  protégés (adb, wifi, mode avion…), shell lecture seule en liste blanche (dumpsys mutants bloqués).
- Journal + rollback testés pour : packages (enabled/disabled/uninstalled), réglages, appops, buckets, Doze.
- Profils : `s24u_debloat`, `s24u_perf`, `s24u_battery`, `s24u_battery_apps`.
- `battery_app_plan` : plan dynamique depuis `dumpsys batterystats` (parseur Android ≤11 et ≥12).

## 4. Non validé / à faire maintenant (dans l'ordre)
1. `adb devices` montre le téléphone en `device` (USB d'abord : accepter l'empreinte RSA, cocher « Toujours autoriser »).
2. Claude Code : approuver le MCP `android-pilot`, puis `device_info` → vérifier modèle `SM-S928B` (ou variante), One UI.
3. `snapshot` de référence (état d'origine du téléphone).
4. `battery_report` → **si `top_apps` est vide, le format One UI diffère** : récupérer la sortie brute
   (`shell_readonly "dumpsys batterystats --charged"`, section *Estimated power use*) et corriger `parse_power_use` dans `core.py`.
5. `apply_profile s24u_debloat dry_run=True max_risk=medium` → vérifier que les packages existent bien.
6. Adapter la liste `keep` de `profiles/s24u_battery_apps.yaml` aux apps réelles (`list_packages third_party`) : banques, etc.
7. Optionnel : sans fil fixe `adb tcpip 5555` + `adb connect <IP>:5555` (saute au reboot du téléphone).

## 5. Données de référence
- Téléphone : Samsung Galaxy S24 Ultra, non rooté. Seb a activé : débogage USB, débogage sans fil,
  « désactiver l'expiration des autorisations ADB ». **À vérifier : Blocage automatique (Auto Blocker) = OFF.**
- PC : Windows 11, Claude Code installé. Remote Control (SebCool-i9-9900k) ne sert pas encore ses dossiers aux
  sessions cloud (MAJ de l'app Claude probablement requise).
- Buckets veille : 5 exempted, 10 active, 20 working_set, 30 frequent, 40 rare, 45 restricted, 50 never
  (seuls active→restricted sont imposables).
- Notes de journal utilisées pour les rollbacks groupés : `profil:<nom>`, `battery_plan`.

## 6. Roadmap
| Étape | Statut |
|---|---|
| Serveur MCP + garde-fous + journal + tests | ✅ |
| Profils debloat / perf / batterie / batterie par app | ✅ (non validés sur device) |
| Install locale D:\AndroidPilot | ⏳ (script prêt) |
| Première connexion + snapshot de référence | ⏳ |
| Validation parseur batterystats sur One UI réel | ⏳ |
| Liste `keep` adaptée | ⏳ |
| Intégration JARVIS / HA (batterie, présence) | 💡 idée |

## 7. Pièges domaine
- **Auto Blocker** One UI bloque ADB → OFF obligatoire.
- Port du Débogage sans fil change à chaque activation ; `adb tcpip 5555` perdu au redémarrage.
- MAJ One UI peut réactiver des packages désactivés → relancer le profil (idempotent).
- Restriction arrière-plan ⇒ notifications push retardées.
- `pm uninstall -k --user 0` ne supprime pas l'APK → `cmd package install-existing` restaure.
- Ne jamais désactiver GOS (`com.samsung.android.game.gos`).
- SDK MCP v2 : les exceptions non `ToolError` sont masquées → passer par le décorateur `mcp.tool` de `server.py`.
- PowerShell 5.1 : scripts `.ps1` en ASCII pur (accents cassés sinon).

## 8. Préférences utilisateur
Français ; direct ; action > questions ; READ → COMPARE → PATCH ; maintenir BRAIN + CHANGELOG ; /CTX = rapport de passation.

## 9. Fichiers
Aucun upload nécessaire : tout est dans le dossier cloné (`CLAUDE.md`, `.claude/HANDOFF.md`, `.claude/ANDROID_PILOT_BRAIN.md`,
`README.md`, `CHANGELOG.md`, `src/`, `profiles/`, `tests/`, `scripts/setup_windows.ps1`).

## 10. Prompt de démarrage (à coller dans Claude Code local)
```
Lis CLAUDE.md puis .claude/HANDOFF.md. On reprend Android Pilot en local : le téléphone est branché en USB.
Vérifie que le serveur MCP android-pilot est actif, fais device_info puis un snapshot de référence,
puis battery_report. Si le rapport batterie est vide, corrige le parseur à partir de la sortie réelle.
Ne modifie rien sur le téléphone sans me montrer le plan.
```
