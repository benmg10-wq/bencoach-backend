#!/usr/bin/env python3
"""Boite a outils Android TV : connexion ADB, sauvegarde, debloat reversible,
lanceur minimal, fonds d'ecran, restauration. Python 3 standard uniquement.

Rien n'est jamais desinstalle (sauf, a la restauration, notre propre lanceur,
si vous le demandez) : les apps sont desactivees avec `pm disable-user`.
"""
import argparse
import concurrent.futures
import datetime
import ipaddress
import json
import os
import platform
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state.json"
BACKUPS = ROOT / "backups"
TOOLS = ROOT / "tools"
SHOTS = ROOT / "shots"
WALLPAPERS = ROOT / "wallpapers"
LAUNCHER_PKG = "com.benmg.tvlauncher"
LAUNCHER_COMPONENT = LAUNCHER_PKG + "/.MainActivity"
UA = "tvtool/1.0 (personal Android TV setup script)"

YES = False
DRY = False
_adb_path = None
_serial = None

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# ---------------------------------------------------------------- etat / adb

def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(**kw):
    st = load_state()
    st.update(kw)
    STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def find_adb():
    global _adb_path
    if _adb_path:
        return _adb_path
    env = os.environ.get("TVTOOL_ADB")
    found = env or shutil.which("adb")
    exe = "adb.exe" if os.name == "nt" else "adb"
    local = TOOLS / "platform-tools" / exe
    if not found and local.exists():
        found = str(local)
    if not found:
        osname = "windows" if os.name == "nt" else ("darwin" if platform.system() == "Darwin" else "linux")
        url = "https://dl.google.com/android/repository/platform-tools-latest-%s.zip" % osname
        print("adb introuvable : telechargement de platform-tools (Google) ...")
        TOOLS.mkdir(exist_ok=True)
        z = TOOLS / "platform-tools.zip"
        urllib.request.urlretrieve(url, z)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(TOOLS)
        z.unlink()
        if os.name != "nt":
            os.chmod(local, 0o755)
        found = str(local)
    _adb_path = found
    return found


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    return p.returncode, (p.stdout or "") + ("" if p.returncode == 0 else (p.stderr or ""))


def devices():
    rc, out = run([find_adb(), "devices"])
    res = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            res.append((parts[0], parts[1]))
    return res


def serial():
    global _serial
    if _serial:
        return _serial
    want = load_state().get("serial")
    devs = devices()
    if want and (want, "device") in devs:
        _serial = want
        return _serial
    if want and ":" in want:
        run([find_adb(), "connect", want], timeout=15)
        if (want, "device") in devices():
            _serial = want
            return _serial
    ok = [s for s, st in devs if st == "device"]
    if len(ok) == 1:
        _serial = ok[0]
        return _serial
    sys.exit("Aucune TV connectee (ou plusieurs). Lancez d'abord : run.cmd connect")


def adb(*args, timeout=60, no_serial=False):
    cmd = [find_adb()]
    if not no_serial:
        cmd += ["-s", serial()]
    return run(cmd + list(args), timeout=timeout)


def sh(command, timeout=60):
    return adb("shell", command, timeout=timeout)[1].strip()


def pm_list(flag):
    out = sh("pm list packages %s" % flag)
    res = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            res.append(line[8:].rsplit("=", 1)[-1])
    return sorted(set(res))


def alive():
    return sh("getprop sys.boot_completed") == "1"


def focus():
    return sh("dumpsys window | grep mCurrentFocus")


def shots_dir():
    b = load_state().get("backup")
    d = (BACKUPS / b / "screenshots") if b else SHOTS
    d.mkdir(parents=True, exist_ok=True)
    return d


def snap(label):
    path = shots_dir() / ("%s-%s.png" % (time.strftime("%H%M%S"), label))
    adb("shell", "screencap -p /sdcard/_tvtool.png")
    adb("pull", "/sdcard/_tvtool.png", str(path))
    adb("shell", "rm -f /sdcard/_tvtool.png")
    if path.exists() and path.stat().st_size > 1000:
        print("  [capture] %s" % path)
        return path
    print("  [capture] impossible (certaines TV bloquent screencap)")
    return None


def ask(prompt, default=""):
    if YES:
        return default
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        ans = ""
    return ans or default


# --------------------------------------------------------------------- connect

def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def port_open(ip, port=5555, timeout=0.6):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def scan_network():
    found = []
    me = local_ip()
    if me:
        net = ipaddress.ip_network(me + "/24", strict=False)
        print("Scan du reseau %s (port ADB 5555) ..." % net)
        hosts = [str(h) for h in net.hosts() if str(h) != me]
        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as ex:
            for ip, ok in zip(hosts, ex.map(port_open, hosts)):
                if ok:
                    found.append(ip + ":5555")
    rc, out = run([find_adb(), "mdns", "services"], timeout=10)
    for m in re.finditer(r"_adb-tls-connect\._tcp\.?\s+(\d+\.\d+\.\d+\.\d+:\d+)", out):
        found.append(m.group(1))
    return sorted(set(found))


def cmd_connect(a):
    find_adb()
    if a.pair:
        print(run([find_adb(), "pair", a.pair[0], a.pair[1]], timeout=30)[1])
    target = a.ip
    if target and ":" not in target:
        target += ":5555"
    if not target:
        usb = [s for s, st in devices() if st in ("device", "unauthorized")]
        if usb and not a.scan:
            target = usb[0]
        else:
            found = scan_network()
            if not found:
                sys.exit(
                    "Aucune TV trouvee. Sur la TV : Parametres > Preferences de l'appareil > A propos > "
                    "cliquer 7 fois sur 'Build', puis Options pour les developpeurs > Debogage USB/ADB "
                    "(et 'Debogage reseau' si present). Relevez l'IP de la TV (Parametres > Reseau) puis : "
                    "run.cmd connect --ip 192.168.x.x   (Android 11+ : run.cmd connect --pair IP:PORT CODE)")
            print("Appareils ADB trouves :")
            for i, f in enumerate(found):
                print("  %d) %s" % (i + 1, f))
            n = 1
            if len(found) > 1:
                n = int(ask("Numero de la TV ? ", "1") or 1)
            target = found[n - 1]
    if ":" in target:
        print(run([find_adb(), "connect", target], timeout=20)[1].strip())
    print("Acceptez la fenetre 'Autoriser le debogage USB ?' sur la TV (cochez 'toujours') ...")
    for _ in range(45):
        st = dict(devices()).get(target)
        if st == "device":
            break
        time.sleep(2)
    else:
        sys.exit("La TV n'a pas autorise la connexion (etat : %s)." % dict(devices()).get(target))
    global _serial
    _serial = target
    save_state(serial=target)
    p = lambda k: sh("getprop " + k)
    print("Connecte : %s %s | Android %s (SDK %s) | %s" % (
        p("ro.product.manufacturer"), p("ro.product.model"),
        p("ro.build.version.release"), p("ro.build.version.sdk"), target))
    snap("connexion")


# ---------------------------------------------------------------------- backup

def home_components():
    out = sh("cmd package query-activities --brief -a android.intent.action.MAIN "
             "-c android.intent.category.HOME")
    return sorted(set(re.findall(r"([\w.]+/[\w.$]+)", out)))


def current_home():
    out = sh("cmd package resolve-activity --brief -a android.intent.action.MAIN "
             "-c android.intent.category.HOME")
    m = re.findall(r"([\w.]+/[\w.$]+)", out)
    return m[-1] if m else ""


def backup_dir(name=None):
    name = name or load_state().get("backup")
    if not name or not (BACKUPS / name).is_dir():
        sys.exit("Aucune sauvegarde. Lancez d'abord : run.cmd backup")
    return BACKUPS / name


def cmd_backup(a):
    d = BACKUPS / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True)
    (d / "screenshots").mkdir()
    save_state(backup=d.name)
    print("Sauvegarde dans %s" % d)
    (d / "props.txt").write_text(sh("getprop", 60), encoding="utf-8")
    for ns in ("global", "secure", "system"):
        (d / ("settings-%s.txt" % ns)).write_text(sh("settings list " + ns), encoding="utf-8")
    flags = {"all": "-f -u", "enabled": "-e", "disabled": "-d", "third-party": "-3", "system": "-s"}
    lists = {}
    for name, fl in flags.items():
        lists[name] = pm_list(fl)
        (d / ("packages-%s.txt" % name)).write_text("\n".join(lists[name]), encoding="utf-8")
    review = [p for p in lists["enabled"]
              if not re.match(r"(android$|com\.android\.|com\.google\.android\.)", p)]
    (d / "packages-a-examiner.txt").write_text("\n".join(review), encoding="utf-8")
    (d / "features.txt").write_text(sh("pm list features"), encoding="utf-8")
    (d / "meminfo.txt").write_text(sh("cat /proc/meminfo | head -5"), encoding="utf-8")
    (d / "home-activities.txt").write_text("\n".join(home_components()), encoding="utf-8")
    manifest = {
        "serial": serial(), "date": datetime.datetime.now().isoformat(),
        "model": sh("getprop ro.product.model"), "android": sh("getprop ro.build.version.release"),
        "home": current_home(), "home_all": home_components(),
        "enabled": lists["enabled"], "disabled": lists["disabled"],
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_restore_scripts(d)
    print("OK : %d paquets (%d actifs, %d deja desactives, %d tiers)." % (
        len(lists["all"]), len(lists["enabled"]), len(lists["disabled"]), len(lists["third-party"])))
    print("Accueil actuel : %s" % manifest["home"])
    print("Liste a examiner (apps non-Google/AOSP) : %s" % (d / "packages-a-examiner.txt"))
    snap("sauvegarde")


# ----------------------------------------------------------------- debloat core

def load_config():
    cfg = json.loads((ROOT / "config" / "debloat.json").read_text(encoding="utf-8"))
    local = ROOT / "config" / "local.json"
    if local.exists():
        extra = json.loads(local.read_text(encoding="utf-8"))
        cfg["categories"] += extra.get("categories", [])
        cfg["protected"] += extra.get("protected", [])
    return cfg


def candidates(cat, enabled, protected):
    out = []
    for p in enabled:
        if any(r.fullmatch(p) for r in protected):
            continue
        if p in cat.get("packages", []) or any(re.fullmatch(x, p) for x in cat.get("patterns", [])):
            out.append(p)
    return sorted(set(out))


def launcher_ready():
    return LAUNCHER_PKG in sh("pm list packages %s" % LAUNCHER_PKG) and LAUNCHER_PKG in current_home()


def disable_pkg(pkg, cat, bdir):
    if DRY:
        print("    (essai) pm disable-user %s" % pkg)
        return True
    out = sh("pm disable-user --user 0 %s" % pkg)
    ok = "disabled" in out.lower() and "exception" not in out.lower()
    if ok:
        with open(bdir / "disabled.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"pkg": pkg, "cat": cat, "t": time.time()}) + "\n")
        print("    desactive : %s" % pkg)
    else:
        print("    ECHEC %s : %s" % (pkg, out.splitlines()[0] if out else "?"))
    return ok


def enable_pkg(pkg):
    out = sh("pm enable %s" % pkg)
    ok = "enabled" in out.lower()
    print("    %s : %s" % ("reactive" if ok else "ECHEC", pkg))
    return ok


def logged_disabled(bdir):
    f = bdir / "disabled.log"
    if not f.exists():
        return []
    return [json.loads(l)["pkg"] for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_restore_scripts(bdir):
    """Scripts autonomes (adb seul) : reactivent tout ce qu'on a desactive."""
    man = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    pkgs = sorted(set(logged_disabled(bdir)))
    ser = man["serial"]
    settings = {}
    ch = bdir / "changes.json"
    if ch.exists():
        settings = json.loads(ch.read_text(encoding="utf-8")).get("settings", {})
    lines = []
    for p in pkgs:
        lines.append("shell pm enable %s" % p)
    for k, v in settings.items():
        lines.append("shell settings put global %s %s" % (k, v) if v is not None
                     else "shell settings delete global %s" % k)
    for stock in man.get("home_all", []):
        if not stock.startswith(LAUNCHER_PKG):
            lines.append("shell cmd package set-home-activity %s" % stock)
            break
    cmd = ["@echo off", "rem Restaure la TV %s (genere automatiquement)" % ser,
           "adb connect %s" % ser] + ["adb -s %s %s" % (ser, l) for l in lines] + [
        "echo Termine. Redemarrez la TV (Parametres > Redemarrer).", "pause"]
    (bdir / "restore.cmd").write_text("\r\n".join(cmd) + "\r\n", encoding="utf-8")
    shl = ["#!/bin/sh", "adb connect %s" % ser] + ["adb -s %s %s" % (ser, l) for l in lines]
    (bdir / "restore.sh").write_text("\n".join(shl) + "\n", encoding="utf-8")


def cmd_debloat(a):
    bdir = backup_dir()
    cfg = load_config()
    protected = [re.compile(x) for x in cfg["protected"]]
    ready = launcher_ready()
    only = set(a.only or [])
    for cat in cfg["categories"]:
        if only and cat["id"] not in only:
            continue
        enabled = pm_list("-e")
        cands = candidates(cat, enabled, protected)
        if not cands:
            continue
        print("\n=== %s ===\n%s" % (cat["title"], cat["description"]))
        if cat.get("requires_launcher") and not ready:
            print("  (ignore : installez d'abord le lanceur : run.cmd launcher)")
            continue
        for p in cands:
            print("   - %s" % p)
        asking = cat.get("ask")
        default = "c" if asking else "o"
        ans = ask("  Desactiver ? [o]ui tout / [n]on / [c]hoisir un par un (defaut %s) : " % default, default)
        if ans.startswith("n"):
            continue
        chosen = cands
        if ans.startswith("c"):
            chosen = [p for p in cands if ask("    Desactiver %s ? [o/N] " % p, "n").startswith("o")]
        done = [p for p in chosen if disable_pkg(p, cat["id"], bdir)]
        if not done or DRY:
            continue
        write_restore_scripts(bdir)
        time.sleep(3)
        print("  Fenetre au premier plan : %s" % focus())
        snap("apres-" + cat["id"])
        if not alive() or ask("  La TV repond normalement (voir la capture) ? [O/n] ", "o").startswith("n"):
            print("  Annulation de cette categorie ...")
            for p in done:
                enable_pkg(p)
    print("\nTermine. Redemarrez la TV pour juger de la vitesse. Restauration : %s" % (bdir / "restore.cmd"))


# ------------------------------------------------------------- vitesse / anim

ANIM_KEYS = ["window_animation_scale", "transition_animation_scale", "animator_duration_scale"]


def cmd_speed(a):
    bdir = backup_dir()
    chf = bdir / "changes.json"
    ch = json.loads(chf.read_text(encoding="utf-8")) if chf.exists() else {}
    saved = ch.setdefault("settings", {})
    for k in ANIM_KEYS:
        if k not in saved:
            old = sh("settings get global " + k)
            saved[k] = None if old in ("", "null") else old
        sh("settings put global %s %s" % (k, a.scale))
    chf.write_text(json.dumps(ch, indent=2), encoding="utf-8")
    write_restore_scripts(bdir)
    print("Animations reglees a x%s (anciennes valeurs sauvegardees)." % a.scale)
    snap("animations")


# ------------------------------------------------------------------ wallpapers

def commons_images(category, limit=40):
    q = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "categorymembers", "gcmtitle": category,
        "gcmtype": "file", "gcmlimit": limit, "prop": "imageinfo", "iiprop": "url|size|mime",
        "iiurlwidth": 1920})
    req = urllib.request.Request("https://commons.wikimedia.org/w/api.php?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    res = []
    for pg in data.get("query", {}).get("pages", {}).values():
        info = (pg.get("imageinfo") or [{}])[0]
        if info.get("mime") in ("image/jpeg", "image/png") and info.get("width", 0) >= 1920 \
                and info["width"] > info.get("height", 1) * 1.4 and info.get("thumburl"):
            res.append(info["thumburl"])
    return res


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def cmd_wallpapers(a):
    WALLPAPERS.mkdir(exist_ok=True)
    cfg = json.loads((ROOT / "config" / "wallpapers.json").read_text(encoding="utf-8"))
    if not a.no_download:
        urls = list(cfg.get("urls", []))
        for cat in cfg.get("commons_categories", []):
            try:
                found = commons_images(cat)
                print("%s : %d images utilisables" % (cat, len(found)))
                random.shuffle(found)
                urls += found[: max(2, a.count // 3)]
            except Exception as e:
                print("%s : ignore (%s)" % (cat, e))
        for i, u in enumerate(urls[: a.count]):
            dest = WALLPAPERS / ("nature%02d.jpg" % (i + 1))
            if dest.exists() and not a.refresh:
                continue
            try:
                download(u, dest)
                print("  telecharge %s" % dest.name)
            except Exception as e:
                print("  echec %s (%s)" % (u, e))
    files = sorted(p for p in WALLPAPERS.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    print("%d fonds d'ecran dans %s" % (len(files), WALLPAPERS))
    if a.no_push or not files:
        return
    if LAUNCHER_PKG not in sh("pm list packages " + LAUNCHER_PKG):
        print("Lanceur non installe : lancez d'abord run.cmd launcher, puis relancez wallpapers --no-download")
        return
    sh("rm -rf /data/local/tmp/wp; mkdir -p /data/local/tmp/wp")
    for f in files:
        adb("push", str(f), "/data/local/tmp/wp/" + re.sub(r"[^A-Za-z0-9._-]", "_", f.name), timeout=180)
    out = sh("run-as %s sh -c 'mkdir -p files/wallpapers && cp /data/local/tmp/wp/* files/wallpapers/ && ls files/wallpapers'" % LAUNCHER_PKG)
    if "No such" in out or "not debuggable" in out or "denied" in out.lower():
        print("run-as indisponible, repli sur le stockage partage ...")
        dst = "/sdcard/Android/data/%s/files/wallpapers" % LAUNCHER_PKG
        sh("mkdir -p " + dst)
        for f in files:
            adb("push", str(f), dst + "/" + re.sub(r"[^A-Za-z0-9._-]", "_", f.name), timeout=180)
    sh("rm -rf /data/local/tmp/wp")
    print("Fonds d'ecran envoyes. Ils defilent toutes les 90 s sur l'accueil.")


# -------------------------------------------------------------------- launcher

def find_apk(given):
    cands = [Path(given)] if given else []
    cands += [ROOT / "tv-launcher.apk", ROOT / "launcher/app/build/outputs/apk/debug/app-debug.apk"]
    cands += sorted(ROOT.glob("*.apk"))
    for c in cands:
        if c.exists():
            return c
    sys.exit("APK introuvable. Telechargez 'tv-launcher-apk' depuis l'onglet Actions de GitHub, "
             "placez app-debug.apk dans tv-toolkit/ (ou utilisez --apk chemin).")


def my_app_package(cfg):
    pats = [re.compile(x) for x in cfg.get("my_apps_patterns", [])]
    for p in pm_list("-3 -e"):
        if any(r.fullmatch(p) for r in pats):
            return p
    third = pm_list("-3 -e")
    return third[0] if third else None


def cmd_launcher(a):
    bdir = backup_dir()
    cfg = load_config()
    apk = find_apk(a.apk)
    print("Installation de %s ..." % apk)
    rc, out = adb("install", "-r", "-g", str(apk), timeout=240)
    print("  " + out.strip().replace("\n", " | "))
    if "Success" not in out:
        sys.exit("Installation echouee.")
    sh("cmd package set-home-activity %s" % LAUNCHER_COMPONENT)
    sh("pm set-home-activity %s" % LAUNCHER_COMPONENT)
    if LAUNCHER_PKG not in current_home():
        print("Le lanceur n'est pas par defaut (accueil = %s)." % current_home())
        stock = [p for p in cfg.get("stock_launchers", []) if p in pm_list("-e")]
        if stock and ask("Desactiver l'accueil d'origine %s (reversible) ? [O/n] " % stock, "o").startswith("o"):
            for p in stock:
                disable_pkg(p, "stock_launcher", bdir)
            write_restore_scripts(bdir)
    hijack = next((c for c in cfg["categories"] if c["id"] == "home_hijack"), {})
    for p in hijack.get("packages", []):
        if p in pm_list("-e"):
            disable_pkg(p, "home_hijack", bdir)
    write_restore_scripts(bdir)
    print("Accueil par defaut : %s" % current_home())
    sh("input keyevent KEYCODE_HOME")
    time.sleep(2)
    snap("accueil")
    test_home(cfg)


def test_home(cfg):
    pkg = my_app_package(cfg)
    if not pkg:
        print("Aucune appli tierce pour tester la touche Home.")
        return
    print("Test Home depuis l'appli %s ..." % pkg)
    sh("monkey -p %s -c android.intent.category.LEANBACK_LAUNCHER 1" % pkg)
    sh("monkey -p %s -c android.intent.category.LAUNCHER 1" % pkg)
    time.sleep(6)
    f1 = focus()
    snap("dans-appli")
    sh("input keyevent KEYCODE_HOME")
    time.sleep(3)
    f2 = focus()
    snap("apres-home")
    print("  avant : %s\n  apres : %s" % (f1, f2))
    print("  RESULTAT : %s" % ("OK, Home ramene a notre accueil" if LAUNCHER_PKG in f2
                               else "ECHEC, Home ne ramene pas a notre accueil"))


def cmd_hometest(a):
    test_home(load_config())


# --------------------------------------------------------------------- restore

def cmd_restore(a):
    bdir = backup_dir(a.backup)
    man = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    base_enabled = set(man["enabled"])
    now_disabled = set(pm_list("-d"))
    todo = sorted((base_enabled & now_disabled) | (set(logged_disabled(bdir)) & now_disabled))
    print("Reactivation de %d paquets ..." % len(todo))
    for p in todo:
        enable_pkg(p)
    chf = bdir / "changes.json"
    if chf.exists():
        for k, v in json.loads(chf.read_text(encoding="utf-8")).get("settings", {}).items():
            sh("settings put global %s %s" % (k, v) if v is not None else "settings delete global " + k)
            print("  reglage %s restaure" % k)
    stock = next((c for c in man.get("home_all", []) if not c.startswith(LAUNCHER_PKG)), "")
    if stock:
        sh("cmd package set-home-activity %s" % stock)
    if not a.keep_launcher and LAUNCHER_PKG in sh("pm list packages " + LAUNCHER_PKG):
        if ask("Desinstaller notre lanceur (com.benmg.tvlauncher) ? [O/n] ", "o").startswith("o"):
            print("  " + adb("uninstall", LAUNCHER_PKG)[1].strip())
    print("Accueil : %s" % current_home())
    snap("restauration")
    print("Termine. Redemarrez la TV.")


def cmd_status(a):
    print("Serie     : %s" % serial())
    print("Accueil   : %s" % current_home())
    print("Fenetre   : %s" % focus())
    print("Desactives: %d paquets" % len(pm_list("-d")))
    snap("statut")


def main():
    global YES, DRY
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="accepte les choix par defaut (non interactif)")
    ap.add_argument("--dry-run", action="store_true", help="n'applique rien")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("connect", help="trouve la TV et se connecte")
    c.add_argument("--ip"); c.add_argument("--scan", action="store_true")
    c.add_argument("--pair", nargs=2, metavar=("IP:PORT", "CODE"))
    c.set_defaults(f=cmd_connect)
    sub.add_parser("backup", help="sauvegarde complete de l'etat").set_defaults(f=cmd_backup)
    d = sub.add_parser("debloat", help="desactive pubs/telemetrie/junk, categorie par categorie")
    d.add_argument("--only", nargs="*"); d.set_defaults(f=cmd_debloat)
    s = sub.add_parser("speed", help="reduit les animations"); s.add_argument("--scale", default="0.5")
    s.set_defaults(f=cmd_speed)
    l = sub.add_parser("launcher", help="installe le lanceur et le met par defaut + test Home")
    l.add_argument("--apk"); l.set_defaults(f=cmd_launcher)
    w = sub.add_parser("wallpapers", help="telecharge et envoie les fonds d'ecran nature")
    w.add_argument("--count", type=int, default=12); w.add_argument("--refresh", action="store_true")
    w.add_argument("--no-download", action="store_true"); w.add_argument("--no-push", action="store_true")
    w.set_defaults(f=cmd_wallpapers)
    sub.add_parser("hometest", help="teste la touche Home depuis une appli").set_defaults(f=cmd_hometest)
    r = sub.add_parser("restore", help="remet la TV comme avant")
    r.add_argument("--backup"); r.add_argument("--keep-launcher", action="store_true")
    r.set_defaults(f=cmd_restore)
    sub.add_parser("status", help="etat actuel + capture").set_defaults(f=cmd_status)
    a = ap.parse_args()
    YES, DRY = a.yes, a.dry_run
    a.f(a)


if __name__ == "__main__":
    main()
