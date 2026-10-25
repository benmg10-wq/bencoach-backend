#!/usr/bin/env python3
"""Faux adb pour tester tvtool.py sans TV. Etat dans $FAKE_ADB_STATE (json)."""
import json, os, re, sys, shlex
SF = os.environ["FAKE_ADB_STATE"]
if not os.path.exists(SF):
    json.dump({
        "pkgs": {p: True for p in [
            "android", "com.android.systemui", "com.google.android.gms", "com.google.android.tvlauncher",
            "com.google.android.tvrecommendations", "com.google.android.katniss", "com.netflix.ninja",
            "com.continental.store", "com.edison.ota", "com.vendor.analytics.sdk", "com.teamsmart.videomanager.tv",
            "com.atlaspro.ontv", "com.mediatek.core", "com.google.android.feedback", "com.google.android.tungsten.setupwraith"]},
        "third": ["com.teamsmart.videomanager.tv", "com.atlaspro.ontv"],
        "home": "com.google.android.tvlauncher/.MainActivity", "settings": {}, "focus": "com.google.android.tvlauncher"}, open(SF, "w"))
S = json.load(open(SF))
a = sys.argv[1:]
def save(): json.dump(S, open(SF, "w"))
if a and a[0] == "-s": a = a[2:]
c = a[0] if a else ""
if c == "devices": print("List of devices attached\n10.0.0.5:5555\tdevice"); sys.exit()
if c in ("connect", "pair", "mdns"): print("connected"); sys.exit()
if c == "pull": open(a[2], "wb").write(b"x" * 2000); sys.exit()
if c == "push": sys.exit()
if c == "install": S["pkgs"]["com.benmg.tvlauncher"] = True; save(); print("Success"); sys.exit()
if c == "uninstall": S["pkgs"].pop("com.benmg.tvlauncher", None); S["home"] = "com.google.android.tvlauncher/.MainActivity"; save(); print("Success"); sys.exit()
cmd = " ".join(a[1:]) if c == "shell" else ""
if cmd.startswith("getprop sys.boot"): print("1")
elif cmd.startswith("getprop ro.product.model"): print("FakeTV")
elif cmd.startswith("getprop"): print("[ro.fake]: [1]")
elif cmd.startswith("settings list"): print("a=b")
elif cmd.startswith("settings get global"): print(S["settings"].get(cmd.split()[-1], "null"))
elif cmd.startswith("settings put global"): S["settings"][cmd.split()[3]] = cmd.split()[4]; save()
elif cmd.startswith("settings delete"): S["settings"].pop(cmd.split()[-1], None); save()
elif cmd.startswith("pm list packages"):
    fl = cmd.split()[3:]; names = [p for p in S["pkgs"] if True]
    if "-e" in fl: names = [p for p in names if S["pkgs"][p]]
    if "-d" in fl: names = [p for p in names if not S["pkgs"][p]]
    if "-3" in fl: names = [p for p in names if p in S["third"] or p == "com.benmg.tvlauncher"]
    tail = [x for x in fl if not x.startswith("-")]
    if tail: names = [p for p in names if tail[0] in p]
    for p in names: print("package:/system/app/x.apk=" + p if "-f" in fl else "package:" + p)
elif cmd.startswith("pm disable-user"):
    p = cmd.split()[-1]; S["pkgs"][p] = False; save(); print("Package %s new state: disabled-user" % p)
elif cmd.startswith("pm enable"):
    p = cmd.split()[-1]; S["pkgs"][p] = True; save(); print("Package %s new state: enabled" % p)
elif "set-home-activity" in cmd: S["home"] = cmd.split()[-1]; S["focus"] = S["home"].split("/")[0]; save()
elif "query-activities" in cmd: print("priority=0\n  com.google.android.tvlauncher/.MainActivity\n  com.benmg.tvlauncher/.MainActivity" if "com.benmg.tvlauncher" in S["pkgs"] else "com.google.android.tvlauncher/.MainActivity")
elif "resolve-activity" in cmd: print("priority=0\n" + S["home"])
elif "mCurrentFocus" in cmd: print("  mCurrentFocus=Window{abc u0 %s/.X}" % S["focus"])
elif cmd.startswith("monkey"): S["focus"] = cmd.split()[2]; save()
elif "KEYCODE_HOME" in cmd: S["focus"] = S["home"].split("/")[0]; save()
elif cmd.startswith("run-as"): print("ok")
