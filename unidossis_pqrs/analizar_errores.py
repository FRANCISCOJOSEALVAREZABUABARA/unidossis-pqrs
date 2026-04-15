#!/usr/bin/env python
"""
═══════════════════════════════════════════════════════════════════
  ANALIZADOR DE ERRORES CON IA — UNIDOSSIS PQRS
  Archivo: analizar_errores.py
  Ubicación: App_PQRS_Unidossis/unidossis_pqrs/

  ¿QUÉ HACE?
  Lee el archivo de logs de la aplicación, agrupa los errores
  repetidos, y genera un reporte en Markdown con sugerencias
  de corrección generadas por IA (Google Gemini).

  ¿CÓMO USARLO?
  1. Activa el entorno virtual: venv\Scripts\activate
  2. Ejecuta: python analizar_errores.py
  3. Revisa el archivo generado: REPORTE_ERRORES.md

  AUTOR: Antigravity AI Assistant
═══════════════════════════════════════════════════════════════════
"""

import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# ─── Configuración ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "logs" / "unidossis.log"
REPORTE_FILE = BASE_DIR / "REPORTE_ERRORES.md"
MAX_ERRORES_ANALIZAR = 20   # Máximo de errores únicos a analizar con IA
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ─── Colores para la terminal ─────────────────────────────────────────────────
VERDE = "\033[92m"
AMARILLO = "\033[93m"
ROJO = "\033[91m"
AZUL = "\033[94m"
RESET = "\033[0m"
NEGRITA = "\033[1m"


def print_banner():
    """Muestra un banner bonito al inicio."""
    print(f"\n{AZUL}{NEGRITA}{'═'*60}{RESET}")
    print(f"{AZUL}{NEGRITA}  🔍 ANALIZADOR DE ERRORES — UNIDOSSIS PQRS{RESET}")
    print(f"{AZUL}{NEGRITA}{'═'*60}{RESET}\n")


def leer_logs() -> list[str]:
    """Lee el archivo de logs y retorna las líneas con errores."""
    if not LOG_FILE.exists():
        print(f"{AMARILLO}⚠️  No se encontró el archivo de logs en:{RESET}")
        print(f"   {LOG_FILE}")
        print(f"\n{AZUL}💡 Tip: La app genera logs al tener su primer error en producción.{RESET}")
        return []

    print(f"{VERDE}✅ Leyendo logs desde:{RESET} {LOG_FILE}")
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        lineas = f.readlines()

    print(f"   📄 Total de líneas en el log: {len(lineas)}")
    return lineas


def extraer_errores(lineas: list[str]) -> list[dict]:
    """
    Extrae y clasifica los errores del log.
    Busca líneas con ERROR, CRITICAL y WARNING.
    """
    errores = []
    patron = re.compile(
        r"\[(?P<fecha>[^\]]+)\]\s+(?P<nivel>ERROR|CRITICAL|WARNING)\s+(?P<modulo>\S+):\s+(?P<mensaje>.+)"
    )

    for linea in lineas:
        match = patron.match(linea.strip())
        if match:
            errores.append({
                "fecha": match.group("fecha"),
                "nivel": match.group("nivel"),
                "modulo": match.group("modulo"),
                "mensaje": match.group("mensaje"),
            })

    return errores


def agrupar_errores(errores: list[dict]) -> list[dict]:
    """Agrupa errores similares y cuenta cuántas veces ocurrieron."""
    contador = Counter()
    primeras_ocurrencias = {}

    for error in errores:
        # Limpiamos el mensaje para agrupar similares
        # (quitamos números específicos, IDs de usuario, etc.)
        clave = re.sub(r'\b\d+\b', 'N', error["mensaje"])
        clave = f"{error['nivel']}|{error['modulo']}|{clave[:150]}"

        contador[clave] += 1
        if clave not in primeras_ocurrencias:
            primeras_ocurrencias[clave] = error

    # Ordenar por frecuencia (los más repetidos primero)
    resultado = []
    for clave, cantidad in contador.most_common(MAX_ERRORES_ANALIZAR):
        entrada = primeras_ocurrencias[clave].copy()
        entrada["cantidad"] = cantidad
        entrada["clave"] = clave
        resultado.append(entrada)

    return resultado


def analizar_con_ia(errores_agrupados: list[dict]) -> dict[str, str]:
    """
    Usa Google Gemini para analizar cada error único y dar sugerencias.
    Retorna un dict: {clave_error: sugerencia_markdown}
    """
    if not GEMINI_API_KEY:
        print(f"\n{AMARILLO}⚠️  Sin GEMINI_API_KEY — se omite análisis de IA.{RESET}")
        print(f"   Configura la variable de entorno GEMINI_API_KEY para obtener sugerencias.")
        return {}

    try:
        from google import genai  # type: ignore
        client = genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        print(f"{AMARILLO}⚠️  Librería google-genai no instalada. Omitiendo IA.{RESET}")
        return {}

    sugerencias = {}
    total = len(errores_agrupados)

    print(f"\n{AZUL}🤖 Analizando {total} errores únicos con IA (Gemini)...{RESET}\n")

    for i, error in enumerate(errores_agrupados, 1):
        nivel = error["nivel"]
        modulo = error["modulo"]
        mensaje = error["mensaje"]
        cantidad = error["cantidad"]

        print(f"   [{i}/{total}] Analizando: {nivel} en {modulo}...", end=" ", flush=True)

        prompt = f"""Eres un experto en Django y Python. Analiza este error de una aplicación web Django llamada UNIDOSSIS PQRS (sistema de gestión de PQRS - Peticiones, Quejas, Reclamos y Sugerencias).

ERROR:
- Nivel: {nivel}
- Módulo: {modulo}
- Mensaje: {mensaje}
- Ocurrió: {cantidad} vez/veces

Responde en español con este formato exacto (máximo 150 palabras):
**¿Qué significa?** (1 oración simple explicando el error)
**¿Por qué ocurre?** (causa más probable)
**¿Cómo corregirlo?** (pasos concretos, numerados)
**Urgencia:** 🔴 Alta / 🟡 Media / 🟢 Baja"""

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            sugerencia = response.text.strip()
            sugerencias[error["clave"]] = sugerencia
            print(f"{VERDE}✅{RESET}")
        except Exception as e:
            sugerencias[error["clave"]] = f"_No se pudo analizar: {e}_"
            print(f"{ROJO}❌{RESET}")

    return sugerencias


def generar_reporte(
    errores_agrupados: list[dict],
    sugerencias: dict[str, str],
    total_lineas_log: int
) -> str:
    """Genera el contenido Markdown del reporte de errores."""

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_errores_log = sum(e["cantidad"] for e in errores_agrupados)

    # Contar por nivel
    por_nivel = Counter(e["nivel"] for e in errores_agrupados)
    criticos = por_nivel.get("CRITICAL", 0)
    errores_c = por_nivel.get("ERROR", 0)
    advertencias = por_nivel.get("WARNING", 0)

    # Emoji de estado global
    estado_emoji = "🔴" if criticos > 0 else ("🟡" if errores_c > 0 else "🟢")
    estado_texto = "CRÍTICO" if criticos > 0 else ("CON ERRORES" if errores_c > 0 else "ESTABLE")

    reporte = f"""# 🔍 Reporte de Errores — UNIDOSSIS PQRS

> **Generado automáticamente con IA el:** `{ahora}`
> **Archivo de log analizado:** `logs/unidossis.log`

---

## {estado_emoji} Estado General del Sistema: {estado_texto}

| Métrica | Valor |
|---------|-------|
| 📄 Líneas totales en el log | `{total_lineas_log:,}` |
| 🔴 CRITICAL (urgente) | `{criticos}` |
| ❌ ERROR | `{errores_c}` |
| ⚠️ WARNING | `{advertencias}` |
| 🔁 Ocurrencias totales detectadas | `{total_errores_log:,}` |
| 🧩 Errores únicos analizados | `{len(errores_agrupados)}` |

---

## 📋 Errores Detectados y Sugerencias de Corrección

"""

    if not errores_agrupados:
        reporte += "> ✅ **¡No se encontraron errores en el log!** El sistema funciona correctamente.\n\n"
    else:
        for i, error in enumerate(errores_agrupados, 1):
            nivel = error["nivel"]
            modulo = error["modulo"]
            mensaje = error["mensaje"]
            cantidad = error["cantidad"]
            fecha = error["fecha"]
            clave = error["clave"]

            # Emoji según nivel
            nivel_emoji = {"CRITICAL": "🔴", "ERROR": "❌", "WARNING": "⚠️"}.get(nivel, "📌")

            reporte += f"""### {nivel_emoji} Error #{i} — {nivel} (ocurrió {cantidad}x)

| Campo | Detalle |
|-------|---------|
| **Módulo** | `{modulo}` |
| **Primera vez** | `{fecha}` |
| **Veces repetido** | `{cantidad}` |
| **Mensaje** | `{mensaje[:200]}{'...' if len(mensaje) > 200 else ''}` |

"""
            if clave in sugerencias:
                reporte += f"**🤖 Análisis de IA:**\n\n{sugerencias[clave]}\n\n"
            else:
                reporte += "_Sin análisis de IA (configura GEMINI_API_KEY para habilitarlo)_\n\n"

            reporte += "---\n\n"

    # Sección de próximos pasos
    reporte += """## 🛠️ Cómo Corregir y Desplegar un Fix

Cuando corrijas un error en el código, sigue estos 3 pasos:

```bash
# 1. Guarda todos los cambios en Git
git add .

# 2. Describe brevemente qué corregiste
git commit -m "Fix: descripción del error corregido"

# 3. Sube a GitHub → Railway actualiza la web automáticamente
git push origin main
```

> ⏱️ Railway tarda ~2 minutos en aplicar el cambio en producción.

---

## 📌 Historial de Reportes

| Fecha | Estado | Errores únicos |
|-------|--------|---------------|
| `{ahora}` | {estado_emoji} {estado_texto} | {len(errores_agrupados)} |

---

*Reporte generado por `analizar_errores.py` — UNIDOSSIS PQRS Pre-Launch Monitor*
""".format(ahora=ahora, estado_emoji=estado_emoji, estado_texto=estado_texto)

    return reporte


def main():
    """Función principal."""
    print_banner()

    # 1. Leer logs
    lineas = leer_logs()
    total_lineas = len(lineas)

    # 2. Extraer errores
    errores = extraer_errores(lineas)
    print(f"   🔍 Errores/Warnings encontrados: {len(errores)}")

    # 3. Agrupar
    errores_agrupados = agrupar_errores(errores)
    print(f"   🧩 Errores únicos para analizar: {len(errores_agrupados)}")

    # 4. Analizar con IA
    sugerencias = analizar_con_ia(errores_agrupados)

    # 5. Generar reporte
    print(f"\n{AZUL}📝 Generando reporte Markdown...{RESET}")
    contenido = generar_reporte(errores_agrupados, sugerencias, total_lineas)

    with open(REPORTE_FILE, "w", encoding="utf-8") as f:
        f.write(contenido)

    print(f"\n{VERDE}{NEGRITA}✅ ¡Reporte generado exitosamente!{RESET}")
    print(f"   📂 Archivo: {REPORTE_FILE}")

    if errores_agrupados:
        print(f"\n{AMARILLO}⚠️  Se encontraron {len(errores_agrupados)} tipo(s) de error.{RESET}")
        print(f"   Revisa el archivo REPORTE_ERRORES.md para ver las sugerencias.\n")
    else:
        print(f"\n{VERDE}🎉 ¡El sistema está limpio! Sin errores críticos detectados.\n{RESET}")


if __name__ == "__main__":
    main()
