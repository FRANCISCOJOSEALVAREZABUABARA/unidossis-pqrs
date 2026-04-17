@echo off
chcp 65001 >nul
title PUBLICAR UNIDOSSIS PQRS
color 0B

echo.
echo =======================================================
echo    PUBLICAR UNIDOSSIS PQRS A PRODUCCION
echo =======================================================
echo.
echo  El deploy a PythonAnywhere es AUTOMATICO via
echo  GitHub Actions al hacer push a main.
echo.

cd /d "c:\Users\Francisco Alvarez\App_PQRS_Unidossis"

:: --- Paso 1: Verificar que hay cambios ---
echo [1/4] Verificando cambios pendientes...
echo.

git status --short
echo.

for /f %%i in ('git status --porcelain ^| find /c /v ""') do set NUM_CAMBIOS=%%i

if "%NUM_CAMBIOS%"=="0" (
    echo No hay cambios nuevos para publicar.
    echo Todo esta sincronizado con GitHub.
    pause
    exit /b 0
)

echo Se encontraron %NUM_CAMBIOS% archivo(s) con cambios.
echo.

:: --- Paso 2: Mostrar detalle de cambios ---
echo =======================================================
echo  [2/4] DETALLE DE CAMBIOS QUE SE VAN A SUBIR:
echo =======================================================
echo.

echo Archivos modificados:
git --no-pager diff --name-status HEAD
echo.

echo Archivos nuevos:
git ls-files --others --exclude-standard
echo.

echo Resumen estadistico:
git --no-pager diff --stat HEAD
echo.

echo Estado vs Produccion (origin/main):
git fetch --quiet 2>nul
git --no-pager log origin/main..HEAD --oneline 2>nul
echo.
echo =======================================================
echo.

set /p CONTINUAR="Deseas continuar con la publicacion? (S/N): "
if /i "%CONTINUAR%"=="N" (
    echo.
    echo Publicacion cancelada.
    pause
    exit /b 0
)
if /i "%CONTINUAR%"=="" (
    echo.
    echo Publicacion cancelada.
    pause
    exit /b 0
)

echo.

:: --- Paso 3: Mensaje de commit ---
echo =======================================================
echo  FORMATO DE COMMIT (Conventional Commits):
echo.
echo    feat:     nueva funcionalidad
echo    fix:      correccion de bug
echo    docs:     documentacion
echo    style:    cambios de estilo o CSS
echo    refactor: reestructuracion de codigo
echo    perf:     mejora de rendimiento
echo    chore:    tareas de mantenimiento
echo    ci:       cambios en CI/CD o configuracion
echo.
echo  Ejemplos:
echo    feat: agregar filtro de busqueda por regional
echo    fix: corregir error en calculo de SLA
echo    chore: actualizar dependencias de seguridad
echo =======================================================
echo.
set /p MENSAJE="Mensaje del commit: "
if "%MENSAJE%"=="" set MENSAJE=chore: actualizacion del sistema

echo.

:: --- Paso 4: Commit + Push ---
echo [3/4] Empaquetando y confirmando cambios...
git add .
git commit -m "%MENSAJE%"

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: No se pudo crear el commit.
    pause
    exit /b 1
)

echo.
echo [4/4] Subiendo a GitHub...
git push

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: No se pudo subir a GitHub. Verifica tu conexion y credenciales.
    pause
    exit /b 1
)

echo.
echo =======================================================
echo  CODIGO SUBIDO EXITOSAMENTE A GITHUB!
echo.
echo  GitHub Actions se encargara automaticamente de:
echo.
echo    [1] Verificar calidad del codigo (Ruff Lint)
echo    [2] Revisar vulnerabilidades de seguridad
echo    [3] Validar configuracion de Django
echo    [4] git pull en PythonAnywhere
echo    [5] Instalar nuevas dependencias (si aplica)
echo    [6] Recargar la webapp
echo.
echo  Tiempo estimado de deploy: 2-4 minutos
echo.
echo  Monitorea el progreso en:
echo  https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/actions
echo.
echo  Verifica el resultado en produccion:
echo  https://Unidossis.pythonanywhere.com
echo =======================================================
echo.
pause
