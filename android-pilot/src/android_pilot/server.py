"""Serveur MCP : expose le téléphone à Claude (Claude Desktop / Claude Code) via stdio."""

from __future__ import annotations

import json
from typing import Any

import functools

try:  # SDK MCP v2
    from mcp.server.mcpserver import Image, MCPServer as Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # SDK MCP v1
    from mcp.server.fastmcp import FastMCP as Server, Image  # type: ignore[no-redef]
    from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[no-redef]
from mcp.types import ToolAnnotations

from .adb import AdbError
from .core import Pilot
from .guard import PROTECTED_PACKAGES

INSTRUCTIONS = """\
Tu pilotes le Samsung Galaxy S24 Ultra de l'utilisateur via ADB (sans root).
Règles :
1. Toujours lire l'état avant de modifier (device_info, package_info, settings_get, apply_profile dry_run).
2. Toute modification passe par les outils journalisés (package_set_state, settings_put, restrict_background,
   apply_profile). Chacune renvoie un change_id annulable via rollback.
3. Faire un snapshot avant une série de modifications.
4. Expliquer ce que fait chaque changement AVANT de l'appliquer, en particulier pour les packages système.
5. shell_unsafe = dernier recours, non journalisé : dire pourquoi et comment revenir en arrière.
6. Pour naviguer dans l'UI : ui_dump (coordonnées 'tap') puis tap/swipe ; screenshot pour vérifier.
"""

_server = Server("android-pilot", instructions=INSTRUCTIONS)
pilot = Pilot()


class _Tools:
    """Décorateur `@mcp.tool` qui transmet à Claude le motif des refus/erreurs attendus
    (sinon le SDK v2 masque le message)."""

    def tool(self, **kw):
        def deco(fn):
            @functools.wraps(fn)
            def wrapper(*a, **k):
                try:
                    return fn(*a, **k)
                except (PermissionError, ValueError, KeyError, AdbError) as e:
                    raise ToolError(f"{type(e).__name__}: {e}") from e
            return _server.tool(**kw)(wrapper)
        return deco

    def run(self):
        _server.run()


mcp = _Tools()

RO = ToolAnnotations(read_only_hint=True, destructive_hint=False)
RW = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)
DANGER = ToolAnnotations(read_only_hint=False, destructive_hint=True)


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


# ----------------------------------------------------------------- connexion
@mcp.tool(annotations=RO)
def adb_status() -> str:
    """Liste les appareils ADB visibles et le serial actuellement ciblé."""
    return f"Serial ciblé : {pilot.adb.serial or '(auto)'}\n{pilot.adb.devices()}"


@mcp.tool(annotations=RW)
def adb_connect(host_port: str) -> str:
    """Se connecte au téléphone en Wi-Fi (Débogage sans fil). host_port ex. '192.168.0.50:37123'
    (port affiché dans Options développeur > Débogage sans fil, il change à chaque activation)."""
    return pilot.adb.connect(host_port)


@mcp.tool(annotations=RW)
def adb_pair(host_port: str, code: str) -> str:
    """Appairage initial (une seule fois) : 'Associer avec un code' dans Débogage sans fil.
    host_port = IP:port DU POPUP D'APPAIRAGE (différent du port de connexion)."""
    return pilot.adb.pair(host_port, code)


# ----------------------------------------------------------------- lecture
@mcp.tool(annotations=RO)
def device_info() -> str:
    """Modèle, Android/One UI, patch sécurité, batterie, stockage, RAM."""
    return _j(pilot.device_info())


@mcp.tool(annotations=RO)
def shell_readonly(command: str) -> str:
    """Commande shell en lecture seule (getprop, dumpsys, pm list/path/dump, settings get/list,
    cmd appops get, df, top, ps, cat /proc|/sys, logcat -d…). Pas de pipes ni redirections."""
    return pilot.shell_readonly(command)


@mcp.tool(annotations=RO)
def list_packages(scope: str = "all", contains: str = "") -> str:
    """Liste les packages. scope : all | system | third_party | disabled | enabled | uninstalled."""
    pkgs = pilot.list_packages(scope, contains)
    return f"{len(pkgs)} packages\n" + "\n".join(f"{p['state'][:3]}  {p['package']}" for p in pkgs)


@mcp.tool(annotations=RO)
def package_info(package: str) -> str:
    """État, version, app système ou non, restriction arrière-plan, bucket de veille d'un package."""
    return _j(pilot.package_info(package))


@mcp.tool(annotations=RO)
def battery_report() -> str:
    """Top consommateurs batterie depuis la dernière charge complète + liste blanche Doze."""
    return _j(pilot.battery_report())


@mcp.tool(annotations=RO)
def settings_get(namespace: str, key: str) -> str:
    """Lit un réglage Android. namespace : system | secure | global."""
    return str(pilot.settings_get(namespace, key))


@mcp.tool(annotations=RO)
def settings_list(namespace: str, contains: str = "") -> str:
    """Liste les réglages d'un namespace (filtre optionnel)."""
    return "\n".join(pilot.settings_list(namespace, contains))


@mcp.tool(annotations=RO)
def protected_packages() -> str:
    """Packages que ce serveur refuse de toucher (sécurité)."""
    return "\n".join(sorted(PROTECTED_PACKAGES))


# ----------------------------------------------------------------- modifications
@mcp.tool(annotations=RW)
def package_set_state(package: str, state: str, reason: str = "") -> str:
    """Change l'état d'une app pour l'utilisateur 0 : enabled | disabled | uninstalled.
    'uninstalled' = désinstallation utilisateur (APK conservé, réversible, sans root). Journalisé."""
    return _j(pilot.set_package_state(package, state, reason))


@mcp.tool(annotations=RW)
def settings_put(namespace: str, key: str, value: str, reason: str = "") -> str:
    """Modifie un réglage Android (system | secure | global). Ancienne valeur journalisée."""
    return _j(pilot.settings_put(namespace, key, value, reason))


@mcp.tool(annotations=RW)
def set_animation_scale(scale: float, reason: str = "") -> str:
    """Règle les 3 échelles d'animation (0 = off, 0.5 = rapide, 1 = défaut)."""
    keys = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")
    return _j([pilot.settings_put("global", k, str(scale), reason or "animations") for k in keys])


@mcp.tool(annotations=RW)
def restrict_background(package: str, restrict: bool = True, reason: str = "") -> str:
    """Empêche (ou ré-autorise) une app de tourner en arrière-plan (appop RUN_ANY_IN_BACKGROUND). Journalisé."""
    return _j(pilot.restrict_background(package, restrict, reason))


@mcp.tool(annotations=RO)
def list_profiles() -> str:
    """Profils d'optimisation disponibles (debloat, perf, batterie…)."""
    return _j(pilot.list_profiles())


@mcp.tool(annotations=RW)
def apply_profile(name: str, dry_run: bool = True, max_risk: str = "low") -> str:
    """Applique un profil. TOUJOURS d'abord dry_run=True et montrer le plan à l'utilisateur.
    max_risk : low | medium | high (les éléments plus risqués sont ignorés)."""
    return _j(pilot.apply_profile(name, dry_run, max_risk))


# ----------------------------------------------------------------- historique
@mcp.tool(annotations=RO)
def journal_list(include_rolled_back: bool = False) -> str:
    """Historique des modifications faites par Claude (avec change_id)."""
    rows = pilot.journal.list(include_rolled_back)
    return "\n".join(
        f"{c.id}  {c.kind:<8} {c.target}  {c.before} → {c.after}  {'[annulé] ' if c.rolled_back else ''}{c.note}"
        for c in rows
    ) or "Aucune modification."


@mcp.tool(annotations=RW)
def rollback(change_id: str) -> str:
    """Annule une modification précise."""
    return _j(pilot.rollback(change_id))


@mcp.tool(annotations=DANGER)
def rollback_all(note_contains: str = "") -> str:
    """Annule toutes les modifications (ordre inverse). Filtre optionnel sur la note, ex. 'profil:debloat'."""
    return _j(pilot.rollback_all(note_contains))


@mcp.tool(annotations=RO)
def snapshot() -> str:
    """Sauvegarde JSON de tous les réglages + états des packages sur le PC. À faire avant une série de changements."""
    return pilot.snapshot()


# ----------------------------------------------------------------- écran
@mcp.tool(annotations=RO)
def screenshot(max_width: int = 720) -> Image:
    """Capture d'écran du téléphone (redimensionnée)."""
    data = pilot.screenshot(max_width)
    return Image(data=data, format="jpeg" if data[:2] == b"\xff\xd8" else "png")


@mcp.tool(annotations=RO)
def ui_dump(only_interactive: bool = True) -> str:
    """Éléments affichés à l'écran avec leurs coordonnées 'tap' (via uiautomator)."""
    return _j(pilot.ui_dump(only_interactive))


@mcp.tool(annotations=RW)
def tap(x: int, y: int) -> str:
    """Tape à l'écran aux coordonnées (pixels réels, cf. ui_dump)."""
    pilot.tap(x, y)
    return "ok"


@mcp.tool(annotations=RW)
def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    """Glisse d'un point à un autre (scroll, ouverture du volet…)."""
    pilot.swipe(x1, y1, x2, y2, duration_ms)
    return "ok"


@mcp.tool(annotations=RW)
def input_text(text: str) -> str:
    """Saisit du texte dans le champ focalisé (ASCII uniquement)."""
    pilot.input_text(text)
    return "ok"


@mcp.tool(annotations=RW)
def keyevent(key: str) -> str:
    """Touche système : HOME, BACK, APP_SWITCH, POWER, VOLUME_UP, ENTER… ou code numérique."""
    pilot.keyevent(key)
    return "ok"


@mcp.tool(annotations=RW)
def launch_app(package: str) -> str:
    """Lance une application par son package."""
    return pilot.launch_app(package)


# ----------------------------------------------------------------- dernier recours
@mcp.tool(annotations=DANGER)
def shell_unsafe(command: str, reason: str) -> str:
    """Commande shell ARBITRAIRE, NON journalisée et NON annulable automatiquement.
    Dernier recours : expliquer à l'utilisateur ce que ça fait et comment revenir en arrière AVANT."""
    r = pilot.adb.shell_raw(command, timeout=120)
    return f"[code {r.code}]\n{r.out}\n{r.err}".strip()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
