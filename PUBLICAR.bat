@echo off
chcp 65001 >nul
title 🚀 PUBLICAR UNIDOSSIS PQRS
color 0B

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║     🚀 PUBLICAR UNIDOSSIS PQRS A PRODUCCION     ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "c:\Users\Francisco Alvarez\App_PQRS_Unidossis"

:: ─── Paso 1: Verificar cambios ───
echo [1/5] 📋 Verificando cambios...
git status --short
echo.

:: Verificar si hay cambios
git diff --quiet --cached
git diff --quiet
if %ERRORLEVEL% equ 0 (
    git status --porcelain | findstr /r "." >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo ✅ No hay cambios nuevos para publicar.
        pause
        exit /b 0
    )
)

:: ─── Paso 2: Pedir mensaje ───
set /p MENSAJE="💬 Describe el cambio (Enter = 'Actualizacion'): "
if "%MENSAJE%"=="" set MENSAJE=Actualizacion del sistema

:: ─── Paso 3: Subir a GitHub ───
echo.
echo [2/5] 📦 Empaquetando cambios...
git add .
git commit -m "%MENSAJE%"

echo.
echo [3/5] ☁️  Subiendo a GitHub...
git push

if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ ERROR: No se pudo subir a GitHub.
    pause
    exit /b 1
)

echo.
echo ✅ Codigo subido a GitHub correctamente.

:: ─── Paso 4: Actualizar PythonAnywhere via API ───
echo.
echo [4/5] 🌐 Ejecutando git pull + pip install en PythonAnywhere...

powershell -ExecutionPolicy Bypass -Command ^
  "$token='8e2dc791cf64cf2b10b6b89e83d4aa72e2ef23ba'; " ^
  "$headers=@{Authorization=\"Token $token\"; 'Content-Type'='application/json'}; " ^
  "try { " ^
  "  $cmd = 'cd ~/unidossis-pqrs && git pull && source ~/.virtualenvs/unidossis/bin/activate && pip install -r unidossis_pqrs/requirements.txt --quiet'; " ^
  "  $body = '{\"command\": \"' + $cmd + '\", \"schedule\": \"once\"}'; " ^
  "  $r = Invoke-RestMethod -Uri 'https://www.pythonanywhere.com/api/v0/user/Unidossis/schedule/' -Method POST -Headers $headers -Body $body -ErrorAction Stop; " ^
  "  Write-Host '   ✅ git pull + pip install programados.' -ForegroundColor Green; " ^
  "} catch { " ^
  "  Write-Host '   ⚠️  Automatico no disponible. Hazlo manualmente:' -ForegroundColor Yellow; " ^
  "  Write-Host '   👉 cd ~/unidossis-pqrs ^&^& git pull' -ForegroundColor White; " ^
  "  Write-Host '   👉 source ~/.virtualenvs/unidossis/bin/activate' -ForegroundColor White; " ^
  "  Write-Host '   👉 pip install -r unidossis_pqrs/requirements.txt' -ForegroundColor White; " ^
  "}"

:: ─── Paso 5: Recargar web app ───
echo.
echo [5/5] 🔄 Recargando web app...

powershell -ExecutionPolicy Bypass -Command ^
  "$token='8e2dc791cf64cf2b10b6b89e83d4aa72e2ef23ba'; " ^
  "$headers=@{Authorization=\"Token $token\"}; " ^
  "try { " ^
  "  Invoke-RestMethod -Uri 'https://www.pythonanywhere.com/api/v0/user/Unidossis/webapps/unidossis.pythonanywhere.com/reload/' -Method POST -Headers $headers | Out-Null; " ^
  "  Write-Host '   ✅ Web app recargada exitosamente!' -ForegroundColor Green; " ^
  "} catch { " ^
  "  Write-Host \"   ⚠️ No se pudo recargar: $($_.Exception.Message)\" -ForegroundColor Yellow; " ^
  "}"

echo.
echo ══════════════════════════════════════════════════
echo  ✅ ¡PUBLICACION COMPLETADA!
echo.
echo  🔗 Verifica en: https://Unidossis.pythonanywhere.com
echo ══════════════════════════════════════════════════
echo.
pause
