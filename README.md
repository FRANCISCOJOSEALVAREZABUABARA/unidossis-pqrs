# 🏥 UNIDOSSIS PQRS — Sistema de Gestión de PQRS

> **Sistema de gestión de Peticiones, Quejas, Reclamos y Sugerencias**  
> Plataforma empresarial con IA integrada para el personal interno de UNIDOSSIS

---

## 📁 Estructura del Proyecto

```
App_PQRS_Unidossis/
├── unidossis_pqrs/               # Código principal Django
│   ├── manage.py
│   ├── tickets/                  # App principal
│   │   ├── views/                # 🆕 Módulos de vistas (refactorizado)
│   │   │   ├── __init__.py       # Re-exporta todo
│   │   │   ├── _helpers.py       # Decoradores y helpers compartidos
│   │   │   ├── auth.py           # Login, logout, contraseñas
│   │   │   ├── dashboard.py      # Dashboard principal
│   │   │   ├── tickets.py        # Detalle de ticket
│   │   │   ├── clientes.py       # Gestión de clientes
│   │   │   ├── portal.py         # Portal del cliente
│   │   │   ├── apis.py           # Endpoints AJAX
│   │   │   ├── reportes.py       # Reportes, Excel, SLA, CSAT
│   │   │   └── monitoreo.py      # Monitoreo, control de cambios, health
│   │   ├── models.py             # Modelos de datos
│   │   ├── ia_engine.py          # Motor de IA (Google Gemini)
│   │   ├── notificaciones.py     # Envío de emails
│   │   ├── urls.py               # Rutas URL
│   │   ├── admin.py              # Panel admin Django
│   │   └── tests.py              # Suite de 67 tests automatizados
│   └── unidossis_pqrs/           # Configuración del proyecto
│       ├── settings.py
│       └── urls.py
├── docs/                         # Documentación y reportes HTML
├── PUBLICAR.bat                  # Script de despliegue a producción
└── requirements.txt
```

---

## 🚀 Inicio Rápido (Desarrollo Local)

```bash
# 1. Activar entorno virtual
.\venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Aplicar migraciones
python manage.py migrate

# 4. Crear superusuario (primera vez)
python manage.py createsuperuser

# 5. Iniciar servidor de desarrollo
python manage.py runserver
```

O simplemente doble clic en `INICIAR_SISTEMA.bat`

---

## 🌐 Despliegue en Producción (PythonAnywhere)

La plataforma está desplegada en **PythonAnywhere** (no Railway).

### Despliegue automático
Doble clic en `PUBLICAR.bat` — hace commit, push y recarga el servidor automáticamente.

### Configuración manual en PythonAnywhere
1. Panel Web → Reload
2. Consola Bash: `git pull origin main && python manage.py migrate`

---

## 🔐 Variables de Entorno Requeridas

Configurar en PythonAnywhere → **Web → Environment Variables** (o `.env` en desarrollo):

| Variable | Descripción | Requerida |
|---|---|---|
| `GEMINI_API_KEY` | Clave API de Google Gemini para el motor IA | ✅ Sí |
| `SECRET_KEY` | Clave secreta de Django | ✅ Sí |
| `DEBUG` | `False` en producción | ✅ Sí |
| `EMAIL_HOST` | Servidor SMTP (ej: `smtp.gmail.com`) | Opcional |
| `EMAIL_HOST_USER` | Usuario del correo | Opcional |
| `EMAIL_HOST_PASSWORD` | Contraseña / App Password del correo | Opcional |
| `EMAIL_PORT` | Puerto SMTP (ej: `587`) | Opcional |

> ⚠️ **NUNCA** hardcodear credenciales en el código fuente.

---

## 🧪 Tests Automatizados

```bash
# Correr todos los tests (67 tests)
python manage.py test tickets -v2

# Correr un módulo específico
python manage.py test tickets.tests.TestAutenticacion
python manage.py test tickets.tests.TestRoles
python manage.py test tickets.tests.TestHealthCheck
```

Módulos de test: `TestModelos`, `TestAutenticacion`, `TestRoles`, `TestDashboard`, `TestTicketDetail`, `TestPortalCliente`, `TestAPIs`, `TestMotorIA`, `TestNotificaciones`, `TestSLA`, `TestHealthCheck`, `TestCSAT`

---

## 🔍 Health Check

El endpoint `/health/` está disponible públicamente para monitoreo:

```bash
curl https://pqrs.unidossis.com.co/health/
```

Respuesta:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok",
  "ia_engine": "configured",
  "stats": { "tickets": 145, "clientes": 23, "usuarios": 8 }
}
```

Se puede configurar en **UptimeRobot** para alertas automáticas.

---

## ⏰ Tareas Programadas (SLA Automático)

Para activar el verificador automático de SLA en **PythonAnywhere**:

1. Ir a **Dashboard → Tasks**
2. Crear nueva tarea con:
   ```
   /home/unidossis/.virtualenvs/venv/bin/python /home/unidossis/unidossis_pqrs/manage.py verificar_sla
   ```
3. Frecuencia: **Diaria** (recomendado: 8:00 AM)

---

## 🏗️ Arquitectura del Sistema

| Capa | Tecnología |
|---|---|
| Framework | Django 5.x |
| Base de datos | SQLite (dev) / PostgreSQL (prod) |
| IA | Google Gemini API |
| Frontend | HTML + Vanilla JS + CSS |
| Autenticación | Django Auth + Rate Limiting propio |
| Despliegue | PythonAnywhere |
| Control de versiones | Git + GitHub |

---

## 📊 Estado del Sistema

| Componente | Estado |
|---|---|
| Tests automatizados | ✅ 67/67 pasando |
| Módulos de vistas | ✅ 10 módulos especializados |
| Health Check | ✅ `/health/` disponible |
| SLA dinámico | ✅ Lee de `ConfiguracionSLA` con caché |
| Recuperación de contraseña | ✅ Híbrida (email + admin) |
| API Key segura | ✅ Solo variables de entorno |
