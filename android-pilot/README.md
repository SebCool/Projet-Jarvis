# Android Pilot — Claude aux commandes du Galaxy S24 Ultra

Serveur **MCP** qui donne à Claude (Claude Desktop ou Claude Code) la main sur le téléphone via **ADB sans fil**,
**sans root** (Knox intact, garantie intacte).

```
Claude Desktop / Claude Code (PC W11 .126)
        │  stdio (MCP)
        ▼
  android-pilot (Python)  ── garde-fous + journal d'annulation
        │  adb (platform-tools)
        ▼  Wi-Fi LAN — Débogage sans fil
  Galaxy S24 Ultra
```

## Ce que Claude peut faire

| Catégorie | Outils | Journalisé / annulable |
|---|---|---|
| Diagnostic | `device_info`, `battery_report`, `list_packages`, `package_info`, `settings_get/list`, `shell_readonly` | lecture seule |
| Apps | `package_set_state` (enabled / disabled / uninstalled), `restrict_background` | ✅ |
| Batterie par app | `battery_report`, `battery_app_plan` (dynamique), `set_standby_bucket`, `set_doze_exempt` | ✅ |
| Réglages | `settings_put`, `set_animation_scale` | ✅ |
| Profils | `list_profiles`, `apply_profile` (dry-run par défaut, filtre de risque) | ✅ |
| Historique | `journal_list`, `rollback`, `rollback_all`, `snapshot` | — |
| Écran | `screenshot`, `ui_dump`, `tap`, `swipe`, `input_text`, `keyevent`, `launch_app` | non (actions UI) |
| Dernier recours | `shell_unsafe` | ❌ non journalisé |

### Garde-fous (non négociables, codés dans `guard.py`)
- **Packages protégés** : SystemUI, téléphonie, IMS/VoLTE, Knox, Play Services, launcher, clavier, Device Care, GOS… → refus.
- **Réglages protégés** : `adb_enabled`, `wifi_on`, `airplane_mode_on`… (tout ce qui couperait l'accès de Claude) → refus.
- **`shell_readonly`** : liste blanche stricte, pas de pipes/redirections, `dumpsys … set/reset` bloqués.
- **Journal** `~/.android-pilot/journal.jsonl` : chaque changement stocke l'état d'avant + la commande inverse.
- « Désinstaller » = `pm uninstall -k --user 0` : l'APK reste dans la partition système → restauration instantanée.

## Installation (une fois)

### 1. Téléphone
1. **Paramètres › À propos du téléphone › Informations sur le logiciel** → taper 7× sur *Numéro de version*.
2. ⚠️ **Paramètres › Sécurité et confidentialité › Blocage automatique (Auto Blocker) → OFF**. Sinon ADB est bloqué.
3. **Options de développement › Débogage sans fil → ON** (sur le Wi-Fi maison).
4. Donner au téléphone une **IP fixe** (bail DHCP statique sur la box).

### 2. PC Windows (.126)
```powershell
# platform-tools Google
winget install Google.PlatformTools        # ou zip : https://developer.android.com/tools/releases/platform-tools
# le projet
cd E:\Antigravity\projects
git clone <repo> ; cd Projet-Jarvis\android-pilot
py -m venv .venv ; .venv\Scripts\pip install -e .
```

### 3. Appairage
Sur le téléphone : *Débogage sans fil › Associer l'appareil avec un code d'association* → noter `IP:port` + code.
```powershell
adb pair 192.168.0.XX:PORT_APPAIRAGE 123456
adb connect 192.168.0.XX:PORT_CONNEXION     # port affiché sur l'écran principal Débogage sans fil
adb tcpip 5555                              # optionnel : port fixe 5555 jusqu'au prochain redémarrage
adb connect 192.168.0.XX:5555
```

### 4. Brancher dans Claude
**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` :
```json
{
  "mcpServers": {
    "android-pilot": {
      "command": "E:\\Antigravity\\projects\\Projet-Jarvis\\android-pilot\\.venv\\Scripts\\python.exe",
      "args": ["-m", "android_pilot.server"],
      "env": {
        "ANDROID_PILOT_ADB": "<résultat de `where adb`>",
        "ANDROID_PILOT_SERIAL": "192.168.0.XX:5555"
      }
    }
  }
}
```
**Claude Code** :
```powershell
claude mcp add android-pilot --env ANDROID_PILOT_SERIAL=192.168.0.XX:5555 -- .venv\Scripts\python.exe -m android_pilot.server
```
Redémarrer Claude Desktop, puis demander : *« fais un device_info de mon téléphone »*.

## Variables d'environnement
| Variable | Rôle | Défaut |
|---|---|---|
| `ANDROID_PILOT_ADB` | chemin de `adb` | `adb` du PATH |
| `ANDROID_PILOT_SERIAL` | appareil ciblé (`IP:port`) | auto si un seul appareil |
| `ANDROID_PILOT_HOME` | journal + snapshots | `~/.android-pilot` |

## Batterie par app — deux approches complémentaires
1. **Profil statique `s24u_battery_apps`** : liste d'apps connues pour être gourmandes (réseaux sociaux, shopping,
   streaming, Samsung non essentiels) → restriction arrière-plan + bucket de veille. Seules les apps installées sont touchées.
2. **Plan dynamique `battery_app_plan`** : part de la **conso réellement mesurée** depuis la dernière charge complète
   (`dumpsys batterystats`), ne cible que les apps tierces, et décide selon la part arrière-plan :
   - `bg_share ≥ 0.4` → restriction arrière-plan ; `≥ 0.7` → bucket `restricted`, sinon `rare` ;
   - app exclue de l'optimisation batterie par l'utilisateur → réintégrée dans Doze ;
   - conso surtout en **service premier plan** (musique, GPS, appel) → **ignorée** (sinon on la casse).

Les deux respectent la liste **`keep`** (dans `profiles/s24u_battery_apps.yaml`) : Home Assistant Companion (JARVIS),
messageries, mail, authentificateurs, Reolink, VPN, GPS, musique, montre, alarmes. **À adapter à tes apps.**

Annulation : `rollback_all(note_contains="battery_plan")` ou `rollback_all(note_contains="profil:s24u_battery_apps")`.

⚠️ Effet de bord assumé : les notifications des apps restreintes arrivent en retard (ou à l'ouverture de l'app).
Le plan dynamique est fiable après une **journée d'usage normal depuis une charge complète**.

## Exemples de demandes
- « Analyse ce qui vide ma batterie depuis la dernière charge et propose des actions. »
- « Fais un snapshot, puis montre-moi le plan du profil s24u_debloat en risque medium. »
- « Empêche Facebook et TikTok de tourner en arrière-plan. »
- « Ouvre les paramètres d'affichage et passe en 120 Hz adaptatif. » (navigation UI)
- « Annule tout ce que tu as fait avec le profil debloat. »

## Limites (sans root)
- Pas d'accès à `/data` des autres apps, pas de modif du kernel / gouverneur CPU, pas de backup d'apps complet.
- Une mise à jour One UI peut réactiver des apps désactivées → relancer le profil (idempotent).
- Le Débogage sans fil se coupe si le téléphone change de Wi-Fi ; `adb tcpip 5555` saute au redémarrage.
- `input_text` : ASCII uniquement (limite Android).

## Tests
```bash
pip install -e ".[dev]" && pytest -q     # faux ADB, aucun téléphone requis
```
