"""Tests sans téléphone : un faux ADB simule pm/settings/appops."""

import shlex

import pytest

from android_pilot.adb import AdbResult
from android_pilot.core import Pilot
from android_pilot.guard import check_readonly
from android_pilot.journal import Journal


class FakeAdb:
    serial = "fake:5555"

    def __init__(self):
        # package -> enabled | disabled | uninstalled
        self.pkgs = {"com.samsung.android.app.tips": "enabled", "com.facebook.system": "enabled",
                     "com.android.systemui": "enabled"}
        self.settings = {("global", "window_animation_scale"): "1.0"}
        self.appops = {}
        self.buckets = {}
        self.doze_user = set()
        self.third_party = {"com.facebook.system"}
        self.batterystats = ""
        self.uids = {}
        self.calls = []

    def _list(self, *flags):
        if "-3" in flags:
            return {p for p in self.third_party if self.pkgs.get(p) not in (None, "uninstalled")}
        if "-u" in flags:
            return set(self.pkgs)
        live = {p for p, s in self.pkgs.items() if s != "uninstalled"}
        if "-d" in flags:
            return {p for p in live if self.pkgs[p] == "disabled"}
        return live

    def package_state(self, p):
        return self.pkgs.get(p, "absent")

    def settings_get(self, ns, key):
        return self.settings.get((ns, key))

    def settings_put(self, ns, key, value):
        if value is None:
            self.settings.pop((ns, key), None)
        else:
            self.settings[(ns, key)] = value

    def getprop(self, k):
        return "x"

    def shell(self, *argv, check=True, timeout=None):
        self.calls.append(argv)
        a = list(argv)
        if a[:2] == ["pm", "disable-user"]:
            self.pkgs[a[-1]] = "disabled"
        elif a[:2] == ["pm", "enable"]:
            self.pkgs[a[-1]] = "enabled"
        elif a[:2] == ["pm", "uninstall"]:
            self.pkgs[a[-1]] = "uninstalled"
        elif a[:3] == ["cmd", "package", "install-existing"]:
            self.pkgs[a[-1]] = "enabled"
        elif a[:2] == ["settings", "put"]:
            self.settings[(a[2], a[3])] = a[4]
        elif a[:2] == ["settings", "delete"]:
            self.settings.pop((a[2], a[3]), None)
        elif a[:3] == ["cmd", "appops", "set"]:
            self.appops[(a[3], a[4])] = a[5]
        elif a[:2] == ["am", "get-standby-bucket"]:
            return str(self.buckets.get(a[2], 10))
        elif a[:2] == ["am", "set-standby-bucket"]:
            names = {"active": 10, "working_set": 20, "frequent": 30, "rare": 40, "restricted": 45}
            self.buckets[a[2]] = names[a[3]]
        elif a[:3] == ["cmd", "deviceidle", "whitelist"]:
            if len(a) == 4:
                (self.doze_user.add if a[3][0] == "+" else self.doze_user.discard)(a[3][1:])
                return ""
            return "\n".join(["system,com.google.android.gms,10150"] + [f"user,{p},10999" for p in self.doze_user])
        elif a[:2] == ["dumpsys", "batterystats"]:
            return self.batterystats
        elif a[:4] == ["cmd", "package", "list", "packages"]:
            return "\n".join(f"package:{p} uid:{u}" for p, u in self.uids.items())
        elif a[:3] == ["cmd", "appops", "get"]:
            v = self.appops.get((a[3], a[4]))
            return f"{a[4]}: {v}; time=+1d" if v and v != "default" else "No operations."
        return ""

    def run(self, *args, timeout=None, binary=False):
        return AdbResult(0, "ok", "")


@pytest.fixture
def pilot(tmp_path):
    return Pilot(FakeAdb(), Journal(tmp_path / "j.jsonl"))


def test_disable_then_rollback(pilot):
    r = pilot.set_package_state("com.samsung.android.app.tips", "disabled")
    assert r["before"] == "enabled" and r["after"] == "disabled"
    pilot.rollback(r["change_id"])
    assert pilot.adb.pkgs["com.samsung.android.app.tips"] == "enabled"
    assert pilot.journal.list() == []


def test_uninstall_from_disabled_restores_disabled(pilot):
    pilot.adb.pkgs["com.facebook.system"] = "disabled"
    r = pilot.set_package_state("com.facebook.system", "uninstalled")
    pilot.rollback(r["change_id"])
    assert pilot.adb.pkgs["com.facebook.system"] == "disabled"


def test_protected_package_refused(pilot):
    with pytest.raises(PermissionError):
        pilot.set_package_state("com.android.systemui", "disabled")
    with pytest.raises(PermissionError):
        pilot.set_package_state("com.samsung.android.knox.foo", "disabled")


def test_setting_rollback_new_key_is_deleted(pilot):
    r = pilot.settings_put("global", "ble_scan_always_enabled", "0")
    assert r["before"] is None
    pilot.rollback(r["change_id"])
    assert ("global", "ble_scan_always_enabled") not in pilot.adb.settings


def test_protected_setting_refused(pilot):
    with pytest.raises(PermissionError):
        pilot.settings_put("global", "adb_enabled", "0")


def test_background_restrict_roundtrip(pilot):
    r = pilot.restrict_background("com.facebook.system", True)
    assert pilot.adb.appops[("com.facebook.system", "RUN_ANY_IN_BACKGROUND")] == "ignore"
    pilot.rollback(r["change_id"])
    assert pilot.adb.appops[("com.facebook.system", "RUN_ANY_IN_BACKGROUND")] == "default"


def test_profile_dry_run_changes_nothing(pilot):
    res = pilot.apply_profile("s24u_debloat", dry_run=True)
    pkgs = {s["package"] for s in res["plan"]}
    assert pkgs == {"com.samsung.android.app.tips", "com.facebook.system"}
    assert all(s == "enabled" for s in pilot.adb.pkgs.values())
    assert all(i["risk"] != "low" for i in res["skipped_by_risk"])


def test_profile_apply_and_rollback_all(pilot):
    pilot.apply_profile("s24u_perf", dry_run=False)
    assert pilot.adb.settings[("global", "window_animation_scale")] == "0.5"
    pilot.rollback_all("profil:s24u_perf")
    assert pilot.adb.settings[("global", "window_animation_scale")] == "1.0"
    assert ("global", "animator_duration_scale") not in pilot.adb.settings


@pytest.mark.parametrize("cmd", [
    "settings put global adb_enabled 0", "pm uninstall com.x.y", "dumpsys battery set level 5",
    "getprop | sh", "cat /sdcard/secret.txt", "cmd appops set a.b X ignore", "rm -rf /sdcard",
    "cmd deviceidle whitelist +com.x.y", "cmd package install-existing com.x.y",
])
def test_readonly_rejects_mutations(cmd):
    with pytest.raises(PermissionError):
        check_readonly(cmd)


@pytest.mark.parametrize("cmd", [
    "getprop ro.product.model", "dumpsys battery", "pm list packages -d", "settings get global wifi_on",
    "cat /proc/meminfo", "cmd appops get com.x.y", "cmd deviceidle whitelist",
])
def test_readonly_accepts(cmd):
    assert check_readonly(cmd)


def test_logcat_forced_dump():
    assert check_readonly("logcat -t 50")[:2] == ["logcat", "-d"]
