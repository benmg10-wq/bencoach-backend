#!/bin/sh
# Test de bout en bout contre le faux adb.
set -e
cd "$(dirname "$0")/.."
export TVTOOL_ADB="$PWD/tests/fake_adb.py" FAKE_ADB_STATE="$(mktemp)"; rm -f "$FAKE_ADB_STATE"
rm -f state.json; rm -rf backups
python3 tvtool.py connect --ip 10.0.0.5
python3 tvtool.py backup
python3 tvtool.py --yes debloat
echo "--- apres debloat :"; python3 -c "import json,os;print([p for p,v in json.load(open(os.environ['FAKE_ADB_STATE']))['pkgs'].items() if not v])"
python3 tvtool.py --yes launcher --apk tests/fake_adb.py
python3 tvtool.py --yes debloat --only launcher_junk home_hijack
python3 tvtool.py speed
python3 tvtool.py --yes restore
echo "--- apres restore :"; python3 -c "import json,os;s=json.load(open(os.environ['FAKE_ADB_STATE']));print([p for p,v in s['pkgs'].items() if not v], s['settings'], s['home'])"
cat backups/*/restore.cmd
rm -rf backups state.json shots
