@echo off
chcp 65001 >nul
where py >nul 2>nul && (py -3 "%~dp0tvtool.py" %* & goto :eof)
python "%~dp0tvtool.py" %*
