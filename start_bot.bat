@echo off
cd /d C:\Users\hp\Downloads\lol-polymarket-bot

:loop
C:\Users\hp\AppData\Local\Programs\Python\Python313\python.exe -m backend.scheduler 2>> bot_d_error.log
timeout /t 10 /nobreak > nul
goto loop
