# 🚀 UNIDOSSIS PQRS — Guía de Pre-Lanzamiento

> **Sistema de gestión de Peticiones, Quejas, Reclamos y Sugerencias**
> Desarrollado para el personal interno de UNIDOSSIS

---

## ¿Cómo está organizado este proyecto?

```
App_PQRS_Unidossis/
├── unidossis_pqrs/          ← Código principal de la aplicación
│   ├── manage.py            ← Comando central de Django
│   ├── analizar_errores.py  ← 🤖 Script de análisis de errores con IA
│   ├── REPORTE_ERRORES.md   ← 📋 Se genera automáticamente
│   ├── requirements.txt     ← Lista de librerías necesarias
│   ├── Procfile             ← Instrucciones para Railway
│   └── railway.toml         ← Configuración de Railway
└── .gitignore               ← Archivos que NO van a GitHub
```

---

## ⚡ Inicio Rápido (Desarrollo Local)

Doble clic en `INICIAR_SISTEMA.bat` — ¡Eso es todo!

---

## 🌐 Despliegue en Railway (Producción)

### Paso 1: Subir a GitHub (una sola vez)

```bash
# En la terminal, desde la carpeta del proyecto:
git init
git add .
git commit -m "🚀 Pre-lanzamiento inicial UNIDOSSIS PQRS"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/unidossis-pqrs.git
git push -u origin main
```

### Paso 2: Conectar Railway

1. Ve a [railway.app](https://railway.app) → Inicia sesión con GitHub
2. Clic en **"New Project"** → **"Deploy from GitHub repo"**
3. Selecciona `unidossis-pqrs`
4. Railway detecta automáticamente que es Django y lo configura

### Paso 3: Configurar Variables de Entorno en Railway

En Railway → tu proyecto → **"Variables"** → agregar:

| Variable | Valor |
|----------|-------|
| `DJANGO_SECRET_KEY` | (genera una en https://djecrety.ir/) |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `tu-app.railway.app` |
| `GEMINI_API_KEY` | Tu clave de Google AI |

### Paso 4: Agregar Base de Datos PostgreSQL

En Railway → **"New"** → **"Database"** → **"PostgreSQL"**
Railway agrega `DATABASE_URL` automáticamente. ¡Listo!

---

## 🔧 Flujo de Trabajo: Corregir un Error

```bash
# 1. Corriges el código en tu computador
# 2. Pruebas que funciona localmente (INICIAR_SISTEMA.bat)
# 3. Subes los cambios:

git add .
git commit -m "Fix: describe brevemente qué corregiste"
git push

# ✅ Railway detecta el cambio y actualiza la web en ~2 minutos
```

---

## 🤖 Analizar Errores con IA

```bash
# Activa el entorno virtual
venv\Scripts\activate

# Entra a la carpeta del proyecto
cd unidossis_pqrs

# Ejecuta el analizador
python analizar_errores.py

# Revisa el reporte generado
# → REPORTE_ERRORES.md
```

---

## 👥 Personal de Prueba (Pre-Lanzamiento)

| Rol | Usuario | Contraseña |
|-----|---------|-----------|
| Administrador | admin | (ver con Francisco) |
| Staff Regional | (crear en /admin) | - |
| Cliente | (crear en /admin) | - |

---

## 📞 Soporte

Para reportar errores o sugerencias durante el prelanzamiento,
contactar al administrador del sistema.

---

*UNIDOSSIS PQRS — Pre-Launch v1.0*
