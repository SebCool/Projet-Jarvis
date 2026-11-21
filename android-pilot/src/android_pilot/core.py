"""Logique métier, indépendante de MCP (testable avec un faux ADB)."""

from __future__ import annotations

import io
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from .adb import Adb, AdbError
from .guard import check_package, check_readonly, check_setting
from .journal import Change, Journal

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"

PackageState = str  # enabled | disabled | uninstalled


class Pilot:
    def __init__(self, adb: Adb | None = None, journal: Journal | None = None):
        self.adb = adb or Adb()
        self.journal = journal or Journal()

    # ------------------------------------------------------------------ infos
    def device_info(self) -> dict[str, Any]:
        p = self.adb.getprop
        battery = self.adb.shell("dumpsys", "battery", check=False)
        bat = dict(re.findall(r"^\s*(level|status|health|temperature|AC powered|USB powered): (.+)$", battery, re.M))
        if "temperature" in bat:
            bat["temperature"] = f"{int(bat['temperature']) / 10:.1f}°C"
        return {
            "serial": self.adb.serial,
            "model": p("ro.product.model"),
            "device": p("ro.product.device"),
            "android": p("ro.build.version.release"),
            "sdk": p("ro.build.version.sdk"),
            "one_ui": p("ro.build.version.oneui"),
            "build": p("ro.build.display.id"),
            "security_patch": p("ro.build.version.security_patch"),
            "knox_warranty_bit": p("ro.boot.warranty_bit"),
            "battery": bat,
            "storage_data": self.adb.shell("df", "-h", "/data", check=False).splitlines()[-1:],
            "memory": self.adb.shell("cat", "/proc/meminfo", check=False).splitlines()[:3],
        }

    def shell_readonly(self, command: str) -> str:
        argv = check_readonly(command)
        r = self.adb.run("shell", " ".join(_q(a) for a in argv), timeout=60)
        out = r.out if r.ok else f"[code {r.code}] {r.err or r.out}"
        return _truncate(out)

    def list_packages(self, scope: str = "all", contains: str = "") -> list[dict[str, str]]:
        flags = {"all": [], "system": ["-s"], "third_party": ["-3"], "disabled": ["-d"], "enabled": ["-e"]}
        if scope == "uninstalled":
            installed = self.adb._list()
            pkgs = sorted(self.adb._list("-u") - installed)
            return [{"package": p, "state": "uninstalled"} for p in pkgs if contains in p]
        if scope not in flags:
            raise ValueError(f"scope ∈ {list(flags) + ['uninstalled']}")
        pkgs = sorted(self.adb._list(*flags[scope]))
        disabled = self.adb._list("-d")
        return [
            {"package": p, "state": "disabled" if p in disabled else "enabled"}
            for p in pkgs
            if contains.lower() in p.lower()
        ]

    def package_info(self, package: str) -> dict[str, Any]:
        dump = self.adb.shell("dumpsys", "package", package, check=False)
        grab = lambda k: (m.group(1).strip() if (m := re.search(rf"{k}=(\S+)", dump)) else None)  # noqa: E731
        return {
            "package": package,
            "state": self.adb.package_state(package),
            "versionName": grab("versionName"),
            "firstInstallTime": grab("firstInstallTime"),
            "lastUpdateTime": grab("lastUpdateTime"),
            "system_app": "SYSTEM" in (grab("pkgFlags") or "") or "flags=[ SYSTEM" in dump,
            "background": self._appop_get(package, "RUN_ANY_IN_BACKGROUND"),
            "standby_bucket": self.adb.shell("am", "get-standby-bucket", package, check=False),
        }

    def battery_report(self) -> dict[str, Any]:
        stats = self.adb.shell("dumpsys", "batterystats", "--charged", check=False, timeout=90)
        # Section "Estimated power use (mAh)" : top consommateurs depuis la dernière charge complète
        top: list[str] = []
        m = re.search(r"Estimated power use \(mAh\):(.*?)(?:\n\s*\n)", stats, re.S)
        if m:
            top = [l.strip() for l in m.group(1).splitlines() if l.strip()][:25]
        uid_map = {}
        for line in self.adb.shell("cmd", "package", "list", "packages", "-U", check=False).splitlines():
            if mm := re.match(r"package:(\S+) uid:(\d+)", line):
                uid_map[mm.group(2)] = mm.group(1)

        def resolve(line: str) -> str:
            mm = re.search(r"UID u0a(\d+)", line)
            if mm:
                uid = str(10000 + int(mm.group(1)))
                return f"{line}  → {uid_map.get(uid, '?')}"
            return line

        return {
            "top_consumers_since_full_charge": [resolve(l) for l in top],
            "deviceidle_whitelist": self.adb.shell("cmd", "deviceidle", "whitelist", check=False).splitlines()[:60],
        }

    def settings_list(self, namespace: str, contains: str = "") -> list[str]:
        check_setting(namespace, "x")
        out = self.adb.shell("settings", "list", namespace, check=False)
        return [l for l in out.splitlines() if contains.lower() in l.lower()]

    def settings_get(self, namespace: str, key: str) -> str | None:
        check_setting(namespace, key)
        return self.adb.settings_get(namespace, key)

    # ----------------------------------------------------- modifications (journalisées)
    def set_package_state(self, package: str, target: PackageState, note: str = "") -> dict[str, Any]:
        check_package(package)
        if target not in ("enabled", "disabled", "uninstalled"):
            raise ValueError("target ∈ enabled | disabled | uninstalled")
        before = self.adb.package_state(package)
        if before == "absent":
            raise ValueError(f"{package} n'existe pas sur ce téléphone")
        if before == target:
            return {"package": package, "state": target, "changed": False}
        for argv in _transition(package, before, target):
            self.adb.shell(*argv)
        after = self.adb.package_state(package)
        if after != target:
            raise AdbError(f"{package} : état attendu {target}, obtenu {after}")
        ch = self.journal.add(Change("package", package, before, after, _transition(package, after, before), note))
        return {"package": package, "before": before, "after": after, "change_id": ch.id}

    def settings_put(self, namespace: str, key: str, value: str, note: str = "") -> dict[str, Any]:
        check_setting(namespace, key)
        before = self.adb.settings_get(namespace, key)
        if before == value:
            return {"setting": f"{namespace}/{key}", "value": value, "changed": False}
        self.adb.settings_put(namespace, key, value)
        undo = [["settings", "delete", namespace, key]] if before is None else [["settings", "put", namespace, key, before]]
        ch = self.journal.add(Change("setting", f"{namespace}/{key}", before, value, undo, note))
        return {"setting": f"{namespace}/{key}", "before": before, "after": value, "change_id": ch.id}

    def restrict_background(self, package: str, restrict: bool, note: str = "") -> dict[str, Any]:
        check_package(package)
        before = self._appop_get(package, "RUN_ANY_IN_BACKGROUND")
        mode = "ignore" if restrict else "allow"
        if before == mode:
            return {"package": package, "background": mode, "changed": False}
        self.adb.shell("cmd", "appops", "set", package, "RUN_ANY_IN_BACKGROUND", mode)
        undo = [["cmd", "appops", "set", package, "RUN_ANY_IN_BACKGROUND", before or "default"]]
        ch = self.journal.add(Change("appop", f"{package}/RUN_ANY_IN_BACKGROUND", before, mode, undo, note))
        return {"package": package, "before": before, "after": mode, "change_id": ch.id}

    def _appop_get(self, package: str, op: str) -> str | None:
        out = self.adb.shell("cmd", "appops", "get", package, op, check=False)
        m = re.search(rf"{op}: (\w+)", out)
        return m.group(1) if m else None

    # ------------------------------------------------------------- profils
    def list_profiles(self) -> list[dict[str, str]]:
        return [
            {"name": p.stem, "description": (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("description", "")}
            for p in sorted(PROFILES_DIR.glob("*.yaml"))
        ]

    def apply_profile(self, name: str, dry_run: bool = True, max_risk: str = "low") -> dict[str, Any]:
        path = PROFILES_DIR / f"{name}.yaml"
        if not path.exists() or path.parent != PROFILES_DIR:
            raise ValueError(f"Profil inconnu : {name}")
        prof = yaml.safe_load(path.read_text(encoding="utf-8"))
        levels = {"low": 0, "medium": 1, "high": 2}
        cap = levels[max_risk]
        plan, results, skipped = [], [], []
        for item in prof.get("packages", []):
            if levels.get(item.get("risk", "high"), 2) > cap:
                skipped.append({**item, "reason": f"risque {item.get('risk')} > {max_risk}"})
                continue
            state = self.adb.package_state(item["package"])
            target = {"disable": "disabled", "uninstall": "uninstalled", "enable": "enabled"}[item["action"]]
            if state in ("absent", target):
                continue
            plan.append({"type": "package", "package": item["package"], "from": state, "to": target, "why": item.get("why", "")})
        for item in prof.get("settings", []):
            cur = self.adb.settings_get(item["namespace"], item["key"])
            if cur != str(item["value"]):
                plan.append({"type": "setting", "setting": f"{item['namespace']}/{item['key']}", "from": cur,
                             "to": str(item["value"]), "why": item.get("why", "")})
        if dry_run:
            return {"profile": name, "dry_run": True, "plan": plan, "skipped_by_risk": skipped}
        note = f"profil:{name}"
        for step in plan:
            try:
                if step["type"] == "package":
                    results.append(self.set_package_state(step["package"], step["to"], note))
                else:
                    ns, key = step["setting"].split("/", 1)
                    results.append(self.settings_put(ns, key, step["to"], note))
            except Exception as e:  # on continue, mais on remonte l'échec
                results.append({"step": step, "error": str(e)})
        return {"profile": name, "dry_run": False, "results": results, "skipped_by_risk": skipped}

    # ------------------------------------------------------------- historique
    def rollback(self, change_id: str) -> dict[str, Any]:
        ch = self.journal.get(change_id)
        if ch.rolled_back:
            return {"change_id": change_id, "already_rolled_back": True}
        for argv in ch.undo:
            self.adb.shell(*argv)
        self.journal.mark_rolled_back(change_id)
        return {"change_id": change_id, "target": ch.target, "restored": ch.before}

    def rollback_all(self, note_contains: str = "") -> list[dict[str, Any]]:
        out = []
        for ch in reversed(self.journal.list()):
            if note_contains in ch.note:
                try:
                    out.append(self.rollback(ch.id))
                except Exception as e:
                    out.append({"change_id": ch.id, "error": str(e)})
        return out

    def snapshot(self, dest_dir: Path | None = None) -> str:
        """Sauvegarde complète réglages + états des packages (référence, pas de restauration auto)."""
        dest_dir = dest_dir or self.journal.path.parent / "snapshots"
        dest_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "build": self.adb.getprop("ro.build.display.id"),
            "settings": {ns: self.adb.shell("settings", "list", ns, check=False).splitlines() for ns in ("system", "secure", "global")},
            "packages_disabled": sorted(self.adb._list("-d")),
            "packages_uninstalled_user0": sorted(self.adb._list("-u") - self.adb._list()),
        }
        path = dest_dir / f"snapshot-{time.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        return str(path)

    # ------------------------------------------------------------- écran / UI
    def screenshot(self, max_width: int = 720) -> bytes:
        png = self.adb.exec_out("screencap", "-p")
        try:
            from PIL import Image as PILImage
        except ImportError:
            return png
        img = PILImage.open(io.BytesIO(png)).convert("RGB")
        if img.width > max_width:
            img = img.resize((max_width, round(img.height * max_width / img.width)))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70)
        return buf.getvalue()

    def ui_dump(self, only_interactive: bool = True) -> list[dict[str, Any]]:
        self.adb.shell("uiautomator", "dump", "/sdcard/android_pilot_ui.xml", timeout=30)
        xml = self.adb.shell("cat", "/sdcard/android_pilot_ui.xml")
        self.adb.shell("rm", "-f", "/sdcard/android_pilot_ui.xml", check=False)
        nodes = []
        for n in ET.fromstring(xml[xml.index("<"):]).iter("node"):
            a = n.attrib
            label = a.get("text") or a.get("content-desc") or ""
            interactive = a.get("clickable") == "true" or a.get("scrollable") == "true" or a.get("checkable") == "true"
            if only_interactive and not (interactive or label):
                continue
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", a.get("bounds", ""))
            center = [(int(m[1]) + int(m[3])) // 2, (int(m[2]) + int(m[4])) // 2] if m else None
            nodes.append({k: v for k, v in {
                "label": label,
                "id": a.get("resource-id", "").split("/")[-1],
                "class": a.get("class", "").split(".")[-1],
                "tap": center,
                "clickable": a.get("clickable") == "true",
                "checked": a.get("checked") if a.get("checkable") == "true" else None,
                "scrollable": a.get("scrollable") == "true" or None,
            }.items() if v not in (None, "", False)})
        return nodes

    def tap(self, x: int, y: int) -> None:
        self.adb.shell("input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.adb.shell("input", "swipe", *(str(int(v)) for v in (x1, y1, x2, y2, duration_ms)))

    def input_text(self, text: str) -> None:
        # `input text` : espaces encodés en %s. Limite Android : pas d'accents ni d'emoji via ADB.
        self.adb.shell("input", "text", text.replace(" ", "%s"))

    def keyevent(self, key: str) -> None:
        self.adb.shell("input", "keyevent", key if key.isdigit() else f"KEYCODE_{key.upper().removeprefix('KEYCODE_')}")

    def launch_app(self, package: str) -> str:
        return self.adb.shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1", check=False)


def _transition(package: str, src: str, dst: str) -> list[list[str]]:
    cmds: list[list[str]] = []
    if src == "uninstalled" and dst != "uninstalled":
        cmds.append(["cmd", "package", "install-existing", "--user", "0", package])
        src = "enabled"
    if dst == "enabled" and src == "disabled":
        cmds.append(["pm", "enable", "--user", "0", package])
    elif dst == "disabled" and src != "disabled":
        cmds.append(["pm", "disable-user", "--user", "0", package])
    elif dst == "uninstalled":
        cmds.append(["pm", "uninstall", "-k", "--user", "0", package])
    return cmds


def _q(a: str) -> str:
    import shlex
    return shlex.quote(a)


def _truncate(s: str, limit: int = 40_000) -> str:
    return s if len(s) <= limit else s[:limit] + f"\n… [tronqué, {len(s) - limit} caractères de plus — affiner la commande]"
