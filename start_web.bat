@echo off
rem ============================================================
rem  Lanceur Windows de l'interface web locale (youtube_clipper)
rem  - demarre FastAPI sur l'hote et le port de server\settings.json
rem  - ouvre le navigateur seulement quand le serveur repond
rem  - construit le frontend une 1re fois si besoin (npm install/build)
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
python -m server.app --open
if errorlevel 1 (
  echo.
  echo ERREUR: le serveur s'est arrete avec un code d'erreur.
  pause
)
endlocal