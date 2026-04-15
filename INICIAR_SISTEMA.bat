@echo off
echo ============================================
echo  UNIDOSSIS PQRS - Migraciones y Servidor
echo ============================================
cd /d "c:\Users\Francisco Alvarez\App_PQRS_Unidossis"
call venv\Scripts\activate
echo.
echo [0/4] Configurando UNIDOSSIS IA...
if "%GEMINI_API_KEY%"=="" (
    echo  [!] GEMINI_API_KEY no esta configurada. La IA funcionara en modo fallback.
    echo  Para activar la IA, ejecuta: set GEMINI_API_KEY=tu_clave_aqui
) else (
    echo  [OK] GEMINI_API_KEY detectada.
)
echo.
echo [1/4] Verificando dependencias...
pip install django openpyxl requests --quiet
echo.
echo [2/4] Creando migraciones...
python unidossis_pqrs\manage.py makemigrations
echo.
echo [3/4] Aplicando migraciones a la base de datos...
python unidossis_pqrs\manage.py migrate
echo.
echo [4/4] Verificando sistema...
python unidossis_pqrs\manage.py check
echo.
echo ============================================
echo  Iniciando servidor de desarrollo...
echo  Abre: http://127.0.0.1:8000/login/
echo  Admin: http://127.0.0.1:8000/admin/
echo ============================================
python unidossis_pqrs\manage.py runserver
pause
