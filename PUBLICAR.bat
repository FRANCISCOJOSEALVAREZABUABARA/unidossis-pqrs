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
echo [4/5] 🌐 Ejecutando git pull en PythonAnywhere...

powershell -ExecutionPolicy Bypass -Command ^
  "$token='8e2dc791cf64cf2b10b6b89e83d4aa72e2ef23ba'; " ^
  "$headers=@{Authorization=\"Token $token\"; 'Content-Type'='application/x-www-form-urlencoded'}; " ^
  "try { " ^
  "  $console = Invoke-RestMethod -Uri 'https://www.pythonanywhere.com/api/v0/user/Unidossis/consoles/' -Method POST -Headers $headers -Body 'executable=bash&arguments=&working_directory=/home/Unidossis'; " ^
  "  $cid = $console.id; " ^
  "  Write-Host \"   Consola $cid creada...\" -ForegroundColor Gray; " ^
  "  Invoke-RestMethod -Uri \"https://www.pythonanywhere.com/api/v0/user/Unidossis/consoles/$cid/send_input/\" -Method POST -Headers $headers -Body 'input=cd+~/unidossis-pqrs+%%26%%26+git+pull%%0A' | Out-Null; " ^
  "  Write-Host '   Git pull enviado, esperando 8 segundos...' -ForegroundColor Gray; " ^
  "  Start-Sleep -Seconds 8; " ^
  "  Invoke-RestMethod -Uri \"https://www.pythonanywhere.com/api/v0/user/Unidossis/consoles/$cid/\" -Method DELETE -Headers $headers -ErrorAction SilentlyContinue | Out-Null; " ^
  "  Write-Host '   ✅ Git pull completado.' -ForegroundColor Green; " ^
  "} catch { " ^
  "  Write-Host \"   ⚠️ Error en git pull: $($_.Exception.Message)\" -ForegroundColor Yellow; " ^
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
