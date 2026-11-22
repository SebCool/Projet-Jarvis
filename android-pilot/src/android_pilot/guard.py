"""Garde-fous : ce que Claude n'a PAS le droit de toucher, et ce qui est en lecture seule."""

from __future__ import annotations

import re
import shlex

# Packages dont la désactivation/désinstallation peut bootlooper le téléphone,
# casser l'appel/SMS, verrouiller l'écran ou déclencher Knox. Jamais touchés.
PROTECTED_PACKAGES: frozenset[str] = frozenset({
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.phone",
    "com.android.server.telecom",
    "com.android.providers.telephony",
    "com.android.providers.settings",
    "com.android.providers.contacts",
    "com.android.providers.media",
    "com.android.providers.media.module",
    "com.android.providers.downloads",
    "com.android.shell",
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller",
    "com.android.permissioncontroller",
    "com.android.inputmethod.latin",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.android.vending",
    "com.google.android.webview",
    "com.android.webview",
    "com.google.android.ext.services",
    "com.android.bluetooth",
    "com.android.networkstack",
    "com.google.android.networkstack",
    "com.android.wifi.resources",
    "com.sec.android.app.launcher",          # One UI Home (sauf si autre launcher installé — à faire à la main)
    "com.samsung.android.honeyboard",         # clavier Samsung (perte de saisie)
    "com.samsung.android.biometrics.app.setting",
    "com.samsung.android.knox.attestation",
    "com.samsung.android.knox.containercore",
    "com.samsung.android.kgclient",           # Knox Guard
    "com.samsung.android.dialer",
    "com.samsung.android.messaging",
    "com.samsung.android.incallui",
    "com.samsung.android.lool",               # Device Care (batterie/RAM)
    "com.samsung.android.sm.devicesecurity",
    "com.samsung.android.providers.context",
    "com.sec.imsservice",                     # VoLTE / VoWiFi
    "com.sec.android.app.SecSetupWizard",
    "com.google.android.setupwizard",
    "com.samsung.android.server.wifi.mobilewips",
    "com.samsung.android.game.gos",           # GOS : désactivation = throttling/bugs jeux connus
    "com.samsung.android.wifi.resources",
    "com.samsung.android.networkstack",
})

PROTECTED_PREFIXES: tuple[str, ...] = (
    "com.android.providers.",
    "com.samsung.android.knox.",
    "com.android.modulemetadata",
)

PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$")


def check_package(package: str) -> None:
    if not PACKAGE_RE.match(package):
        raise ValueError(f"Nom de package invalide : {package!r}")
    if package in PROTECTED_PACKAGES or package.startswith(PROTECTED_PREFIXES):
        raise PermissionError(f"{package} est protégé (risque bootloop / téléphonie / Knox). Refusé.")


SETTINGS_NAMESPACES = ("system", "secure", "global")
SETTING_KEY_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")

# Réglages qui peuvent verrouiller l'utilisateur hors de son téléphone ou couper ADB.
PROTECTED_SETTINGS: frozenset[tuple[str, str]] = frozenset({
    ("global", "adb_enabled"),
    ("global", "adb_wifi_enabled"),
    ("global", "development_settings_enabled"),
    ("secure", "lockscreen.disabled"),
    ("global", "device_provisioned"),
    ("secure", "user_setup_complete"),
    ("global", "airplane_mode_on"),           # couperait le Wi-Fi donc ADB sans fil
    ("global", "wifi_on"),
})


def check_setting(namespace: str, key: str) -> None:
    if namespace not in SETTINGS_NAMESPACES:
        raise ValueError(f"namespace doit être l'un de {SETTINGS_NAMESPACES}")
    if not SETTING_KEY_RE.match(key):
        raise ValueError(f"Clé de réglage invalide : {key!r}")
    if (namespace, key) in PROTECTED_SETTINGS:
        raise PermissionError(f"{namespace}/{key} est protégé (couperait l'accès ADB ou le verrouillage). Refusé.")


# Commandes shell autorisées en lecture seule (premier mot + sous-commande éventuelle).
READONLY_COMMANDS: dict[str, tuple[str, ...] | None] = {
    "getprop": None,
    "dumpsys": None,
    "df": None,
    "du": None,
    "free": None,
    "uptime": None,
    "top": None,
    "ps": None,
    "cat": None,          # restreint plus bas à /proc et /sys
    "ls": None,
    "id": None,
    "date": None,
    "uname": None,
    "wm": ("size", "density"),
    "pm": ("list", "path", "dump", "get-max-users"),
    "cmd": ("package", "deviceidle", "appops"),
    "settings": ("get", "list"),
    "appops": ("get",),
    "am": ("get-standby-bucket", "get-inactive"),
    "logcat": None,       # forcé en -d (dump) plus bas
}

# Certains dumpsys modifient l'état (`dumpsys battery set level 5`, `dumpsys deviceidle force-idle`…)
DUMPSYS_MUTATING = frozenset({"set", "unplug", "reset", "force-idle", "unforce", "step", "enable", "disable",
                              "whitelist", "except-idle-whitelist", "tempwhitelist", "clear", "--reset"})

FORBIDDEN_CHARS = set(";|&`$><\n")


def check_readonly(command: str) -> list[str]:
    """Valide qu'une commande est en lecture seule. Retourne argv. Lève PermissionError sinon."""
    if any(c in FORBIDDEN_CHARS for c in command):
        raise PermissionError("Pipes, redirections et chaînage interdits en mode lecture seule.")
    argv = shlex.split(command)
    if not argv:
        raise ValueError("Commande vide")
    head = argv[0]
    if head not in READONLY_COMMANDS:
        raise PermissionError(f"`{head}` n'est pas dans la liste lecture seule. Utiliser shell_unsafe.")
    subs = READONLY_COMMANDS[head]
    if subs is not None:
        if len(argv) < 2 or argv[1] not in subs:
            raise PermissionError(f"`{head}` autorisé seulement avec : {', '.join(subs)}")
    if head == "cmd" and argv[1] == "appops" and (len(argv) < 3 or argv[2] != "get"):
        raise PermissionError("`cmd appops` autorisé seulement avec `get`.")
    if head == "cmd" and argv[1] == "package" and (len(argv) < 3 or argv[2] not in ("list", "resolve-activity", "query-activities")):
        raise PermissionError("`cmd package` autorisé seulement avec list/resolve-activity/query-activities.")
    if head == "cmd" and argv[1] == "deviceidle" and argv[2:] not in (["whitelist"], ["get", "deep"], ["get", "light"]):
        raise PermissionError("`cmd deviceidle` autorisé seulement : `whitelist` (sans argument) ou `get deep|light`.")
    if head == "dumpsys" and any(a in DUMPSYS_MUTATING for a in argv[2:]):
        raise PermissionError("Ce `dumpsys` modifie l'état (set/unplug/reset/force-idle…). Utiliser shell_unsafe.")
    if head == "cat" and not all(a.startswith(("/proc/", "/sys/")) for a in argv[1:]):
        raise PermissionError("`cat` limité à /proc et /sys.")
    if head == "logcat" and "-d" not in argv:
        argv.insert(1, "-d")
    if head == "top" and "-n" not in argv:
        argv[1:1] = ["-b", "-n", "1"]
    return argv
