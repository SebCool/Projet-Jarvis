# ANDROID_PILOT_BRAIN

## Rôle de Claude
Pilote du Samsung Galaxy S24 Ultra de Seb via le serveur MCP `android-pilot` (ADB sans fil, sans root).
Méthode : READ → COMPARE → PATCH. Snapshot avant toute série de modifs. Dry-run avant tout profil.

## État technique
- Version : 0.1.0 — code dans `Projet-Jarvis/android-pilot/` (branche ccr-355f178b-z54gah)
- Stack : Python ≥3.10, `mcp` (v2 : `mcp.server.mcpserver.MCPServer`, fallback v1 FastMCP), pyyaml, pillow
- Tests : `pytest -q` → 25 passés (faux ADB)
- Hôte prévu : PC W11 .126 (Claude Desktop + platform-tools)
- Journal : `~/.android-pilot/journal.jsonl` ; snapshots : `~/.android-pilot/snapshots/`

## Fichiers
| Fichier | Rôle |
|---|---|
| `src/android_pilot/adb.py` | wrapper subprocess adb, états packages |
| `src/android_pilot/guard.py` | packages/réglages protégés, liste blanche lecture seule |
| `src/android_pilot/journal.py` | journal JSONL + rollback |
| `src/android_pilot/core.py` | logique métier (testable) |
| `src/android_pilot/server.py` | outils MCP |
| `profiles/*.yaml` | profils d'optimisation (risk low/medium/high) |

## Roadmap
| Étape | Statut |
|---|---|
| Scaffold serveur + garde-fous + tests | ✅ |
| Install sur .126 + appairage téléphone | ⏳ à faire par Seb |
| Premier `device_info` réel + snapshot de référence | ⏳ |
| Valider noms de packages du profil debloat sur le vrai téléphone (`list_packages`) | ⏳ |
| Profil batterie par app (restrict_background ciblé après `battery_report`) | 🔜 |
| Intégration JARVIS/HA (batterie, présence) — optionnel | 💡 |

## Pièges domaine
- **Auto Blocker (Blocage automatique)** One UI 6+ bloque ADB → doit être OFF.
- Port du Débogage sans fil change à chaque activation ; `adb tcpip 5555` = port fixe jusqu'au reboot.
- MAJ One UI peut réactiver des packages désactivés → relancer le profil.
- Ne jamais désactiver GOS (`com.samsung.android.game.gos`) : throttling/bugs connus.
- `pm uninstall --user 0` ≠ suppression : APK conservé, `cmd package install-existing` restaure.
- SDK MCP v2 masque les exceptions non-ToolError → wrapper `_Tools` dans server.py convertit les erreurs attendues.
