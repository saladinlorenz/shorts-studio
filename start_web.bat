@echo off
rem ============================================================
rem  Lanceur Windows de l'interface web locale (youtube_clipper)
rem  - demarre FastAPI sur l'hote et le port de server\settings.json
rem  - ouvre le navigateur seulement quand le serveur repond
rem  - construit le frontend une 1re fois si besoin (npm install/build)
rem  - relance le serveur si le watchdog detecte une panne (code de sortie 3)
rem  Aucun telechargement n'est fait au demarrage, sauf la premiere
rem  construction du frontend (npm install) si web\node_modules est absent.
rem ============================================================
setlocal
cd /d "%~dp0"

rem Node.js portable du projet, au meme endroit que server\render.py le cherche
if exist "%~dp0..\_tools\node\node.exe" set "PATH=%~dp0..\_tools\node;%PATH%"

where python >nul 2>&1
if errorlevel 1 (
  echo ERREUR: Python est introuvable dans le PATH. Installez Python 3.12+
  echo en cochant "Add python.exe to PATH", puis relancez ce fichier.
  pause
  exit /b 1
)

if not exist "web\dist\index.html" (
  echo [1/2] Construction du frontend (premiere execution^)...
  pushd web
  if not exist node_modules (
    call npm install --no-audit --no-fund
    if errorlevel 1 (
      echo ERREUR: npm install a echoue.
      popd
      pause
      exit /b 1
    )
  )
  call npm run build
  if errorlevel 1 (
    echo ERREUR: echec du build du frontend.
    popd
    pause
    exit /b 1
  )
  popd
) else (
  echo [1/2] Frontend deja construit (web\dist^).
)

echo [2/2] Demarrage du serveur...
echo       Le navigateur s'ouvrira des que le serveur repond.
echo       Ctrl+C dans cette fenetre arrete l'application.
set "FIRST_RUN=1"
:server_loop
if defined FIRST_RUN (
  python -m server.app --open
) else (
  python -m server.app
)
set "EXIT_CODE=%errorlevel%"
rem Code 3 : le watchdog a constate que le serveur ne repond plus (WinError 64).
rem On relance une instance neuve ; le navigateur ne s'ouvre qu'au 1er demarrage.
if "%EXIT_CODE%"=="3" (
  echo.
  echo [watchdog] Le serveur ne repondait plus : redemarrage automatique dans 3 secondes...
  set "FIRST_RUN="
  %SystemRoot%\System32\timeout.exe /t 3 /nobreak >nul 2>&1
  goto server_loop
)
if not "%EXIT_CODE%"=="0" (
  echo.
  echo ERREUR: le serveur s'est arrete avec le code %EXIT_CODE%.
  pause
)
endlocal