"""Tests du profil batterie par app et du plan dynamique."""

import pytest

from android_pilot.core import Pilot, parse_power_use
from android_pilot.journal import Journal
from test_core import FakeAdb

STATS_A14 = """\
Battery History (2% used, 10KB used of 4096KB, 120 strings using 9KB):
  Estimated power use (mAh):
    Capacity: 5000, Computed drain: 1820, actual drain: 1700-1900
    Global
      screen: 610 apps: 610 duration: 5h 2m
      cell: 120 apps: 80
    UID u0a301: 320 fg: 40.0 bg: 260 fgs: 20.0 cached: 0 ( cpu=300 )
    UID u0a302: 150 fg: 140 bg: 10.0 fgs: 0 cached: 0 ( cpu=140 )
    UID u0a303: 400 fg: 20.0 bg: 30.0 fgs: 350 cached: 0 ( cpu=50 gps=300 )
    UID u0a304: 90.0 fg: 0 bg: 90.0 fgs: 0 cached: 0 ( cpu=90 )
    UID 1000: 200 fg: 0 bg: 200 ( cpu=200 )
    UID u0a305: 5.0 fg: 0 bg: 5.0 ( cpu=5 )

  All kernel wake locks:
    Kernel Wake lock PowerManagerService.WakeLocks: 1h
"""

STATS_A11 = """\
  Estimated power use (mAh):
    Capacity: 4500, Computed drain: 900, actual drain: 800-950
    Screen: 300
    Uid u0a12: 120 ( cpu=100 wake=20 )
    Uid 1000: 80.0 ( cpu=80 )
  All partial wake locks:
"""


def test_parse_android14():
    r = parse_power_use(STATS_A14, {10301: ["com.zhiliaoapp.musically"], 1000: ["android"]})
    assert r["capacity"] == 5000 and r["computed_drain"] == 1820
    top = r["apps"][0]
    assert top["uid"] == 10303 and top["fgs_mah"] == 350
    tiktok = next(a for a in r["apps"] if a["uid"] == 10301)
    assert tiktok["packages"] == ["com.zhiliaoapp.musically"] and tiktok["bg_mah"] == 260
    assert len(r["apps"]) == 6  # rien de la section kernel wake locks


def test_parse_android11_no_bg_split():
    r = parse_power_use(STATS_A11, {10012: ["com.x.y"]})
    assert r["apps"][0] == {"uid": 10012, "packages": ["com.x.y"], "mah": 120.0, "bg_mah": None, "fgs_mah": None}


@pytest.fixture
def pilot(tmp_path):
    adb = FakeAdb()
    adb.batterystats = STATS_A14
    adb.pkgs.update({p: "enabled" for p in ("com.zhiliaoapp.musically", "com.instagram.android",
                                            "com.strava", "com.temu.fake", "io.homeassistant.companion.android")})
    adb.third_party |= {"com.zhiliaoapp.musically", "com.instagram.android", "com.strava", "com.temu.fake",
                        "io.homeassistant.companion.android"}
    adb.uids = {"com.zhiliaoapp.musically": 10301, "com.instagram.android": 10302, "com.strava": 10303,
                "io.homeassistant.companion.android": 10304, "com.temu.fake": 10305}
    adb.doze_user = {"com.zhiliaoapp.musically"}
    return Pilot(adb, Journal(tmp_path / "j.jsonl"))


def test_dynamic_plan(pilot):
    res = pilot.battery_app_plan(dry_run=True)
    plan = {p["package"]: p for p in res["plan"]}
    # TikTok : 81 % en arrière-plan → restriction + bucket restricted + retrait exemption Doze
    ops = {a["op"]: a["to"] for a in plan["com.zhiliaoapp.musically"]["actions"]}
    assert ops == {"background": "restrict", "bucket": "restricted", "doze": "optimize"}
    # Instagram : conso surtout écran allumé → pas de restriction arrière-plan, juste bucket rare
    assert {a["op"]: a["to"] for a in plan["com.instagram.android"]["actions"]} == {"bucket": "rare"}
    ignored = {i["package"]: i["reason"] for i in res["ignored"]}
    assert "premier plan" in ignored["com.strava"]          # GPS en service premier plan
    assert ignored["io.homeassistant.companion.android"] == "liste keep"
    assert "com.temu.fake" not in plan                     # sous min_mah
    assert pilot.journal.list() == []                      # dry-run : rien d'écrit


def test_dynamic_apply_and_rollback(pilot):
    pilot.battery_app_plan(dry_run=False)
    adb = pilot.adb
    assert adb.appops[("com.zhiliaoapp.musically", "RUN_ANY_IN_BACKGROUND")] == "ignore"
    assert adb.buckets["com.zhiliaoapp.musically"] == 45
    assert "com.zhiliaoapp.musically" not in adb.doze_user
    pilot.rollback_all("battery_plan")
    assert adb.buckets["com.zhiliaoapp.musically"] == 10
    assert "com.zhiliaoapp.musically" in adb.doze_user
    assert adb.appops[("com.zhiliaoapp.musically", "RUN_ANY_IN_BACKGROUND")] == "default"


def test_static_profile(pilot):
    res = pilot.apply_profile("s24u_battery_apps", dry_run=True, max_risk="medium")
    plan = {p["package"]: p for p in res["plan"]}
    assert set(plan) == {"com.zhiliaoapp.musically", "com.instagram.android"}
    low = pilot.apply_profile("s24u_battery_apps", dry_run=True, max_risk="low")
    assert {p["package"] for p in low["plan"]} == {"com.zhiliaoapp.musically"}
    pilot.apply_profile("s24u_battery_apps", dry_run=False, max_risk="low")
    assert pilot.adb.buckets["com.zhiliaoapp.musically"] == 45
    assert len(pilot.journal.list()) == 2


def test_keep_list_never_in_profile_apps():
    import yaml
    from android_pilot.core import PROFILES_DIR
    prof = yaml.safe_load((PROFILES_DIR / "s24u_battery_apps.yaml").read_text(encoding="utf-8"))
    assert not set(prof["keep"]) & {a["package"] for a in prof["apps"]}


def test_system_bucket_not_settable(pilot):
    pilot.adb.buckets["com.zhiliaoapp.musically"] = 5  # exempted
    with pytest.raises(PermissionError):
        pilot.set_standby_bucket("com.zhiliaoapp.musically", "rare")
