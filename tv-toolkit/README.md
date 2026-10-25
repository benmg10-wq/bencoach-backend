# Boite a outils Android TV (Continental Edison)

Debloat **reversible** + accueil minimal style Apple TV (dock d'applis favorites, fonds nature qui defilent).
Rien n'est desinstalle : les apps sont desactivees (`pm disable-user`) et se reactivent a tout moment.

## Prerequis (Windows)
1. Python 3 : `winget install Python.Python.3.12` (ou python.org). `adb` est telecharge automatiquement.
2. Sur la TV : Parametres > Preferences de l'appareil > A propos > cliquer 7 fois sur **Build**, puis
   Options pour les developpeurs > activer **Debogage USB / ADB** (et *Debogage reseau* si present).
3. PC et TV sur le meme Wi-Fi. Ouvrez un terminal dans ce dossier.

## Ordre des etapes (chaque etape prend des captures d'ecran de la TV)
```
run.cmd connect                 # trouve la TV sur le reseau et se connecte (acceptez la fenetre sur la TV)
run.cmd backup                  # SAUVEGARDE complete, cree restore.cmd. A faire avant tout.
run.cmd launcher --apk app-debug.apk   # installe l'accueil, le met par defaut, teste le bouton Home
run.cmd debloat                 # desactive pubs/telemetrie/junk ; demande avant les apps utiles
run.cmd speed                   # animations x0.5 (reversible)
run.cmd wallpapers              # telecharge et envoie des fonds nature
run.cmd hometest                # re-teste Home depuis une appli
```
`run.cmd --dry-run debloat` montre ce qui serait fait sans rien changer.

L'APK du lanceur est compile par GitHub : onglet **Actions > Build TV launcher > tv-launcher-apk**.

## Restauration
- `run.cmd restore` : reactive tout, remet les animations et l'accueil d'origine, propose de retirer le lanceur.
- Ou, sans Python : `backups\<date>\restore.cmd` (juste `adb`). Redemarrez ensuite la TV.

## Dock
Fleches pour naviguer, OK pour lancer, **appui long sur OK** pour retirer un favori, tuile **+** pour en ajouter.
Par defaut : AtlasPro ONTV, Iron Max IPTV, SmartTube (detectes par leur nom).

## Personnaliser
- `config/debloat.json` : categories. Ajoutez les votres dans `config/local.json` (meme format).
- `backups/<date>/packages-a-examiner.txt` : apps du fabricant a passer en revue.
- Mettez vos propres images dans `wallpapers/`, puis `run.cmd wallpapers --no-download`.
