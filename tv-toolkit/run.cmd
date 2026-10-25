@echo off
chcp 65001 >nul
where py >nul 2>nul && (py -3 "%~dp0tvtool.py" %* & goto :end)
where python >nul 2>nul && (python "%~dp0tvtool.py" %* & goto :end)
echo Python n'est pas installe. Ouvrez l'Invite de commandes et tapez : winget install Python.Python.3.12
echo Puis refermez et double-cliquez de nouveau sur ce fichier.
:end
pause
