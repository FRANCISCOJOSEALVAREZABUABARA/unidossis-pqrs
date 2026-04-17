import os
import json
import requests

# Configuracion del motor UNIDOSS.IA
# Configuración segura: la API key debe definirse como variable de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDPzRKxXAM9eOACGwDn0si1HXZF6r-OmU0")
MODELO_IA = "gemini-1.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_IA}:generateContent?key={GEMINI_API_KEY}" if GEMINI_API_KEY else None


def llamar_gemini(prompt, temperature=0.1):
    """Llamada directa a Gemini via HTTP REST. Temperatura baja para mayor precision analitica."""
    if not API_URL:
        return None  # Sin API key configurada, usar fallback
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
            }
        }
        response = requests.post(API_URL, json=payload, timeout=20)
        if response.status_code == 200:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return None
    except Exception:
        return None


def _construir_prompt_clasificacion(asunto, descripcion, contexto_feedback=""):
    """
    Construye el prompt de clasificación con aprendizaje de correcciones anteriores.
    El contexto_feedback inyecta patrones aprendidos de correcciones humanas.
    """
    aprendizaje = ""
    if contexto_feedback:
        aprendizaje = f"""
APRENDIZAJE DE CORRECCIONES ANTERIORES (ejemplos reales corregidos por el equipo Unidossis):
{contexto_feedback}

IMPORTANTE: Usa estos ejemplos como guía para mejorar tu clasificación. Si el caso actual
es similar a alguno de los ejemplos, prioriza la clasificación que el equipo humano usó.
"""

    return f"""Eres UNIDOSSIS IA, experto en PQRS farmacéuticas para Unidossis Colombia.
Clasifica el siguiente caso según la Resolución 1403, 0444 y 2200 de Colombia.
{aprendizaje}
CASO A CLASIFICAR:
  Asunto: {asunto}
  Descripción: {descripcion}

Devuelve SOLO un JSON válido (sin markdown, sin texto extra) con exactamente estos campos:
{{
  "linea": "<uno de: administrativo, dosis_anticipada, esteriles, magistral, npt, npt_vet, oncologia, solidos, todas, logistica_linea, logistica_blitz>",
  "proceso": "<uno de: gerencia, produccion, comercial, logistica, administrativa, talento, sst, calidad>",
  "tipificacion": "<uno de: producto_no_conforme, no_conformidad_entrega, farmacovigilancia, diferencia_inventario, entrega_fuera_acuerdo, error_almacenamiento, error_interpretacion, error_embalaje, error_empaque, error_re_empaque, error_etiqueta, error_despacho, incumplimiento, resultados_micro, solicitud_cliente>",
  "criticidad": "<uno de: critica, mayor, menor, informativa>",
  "analisis_ia": "<Breve explicación profesional de la clasificación, máximo 2 oraciones>"
}}
"""


def _parsear_respuesta_json(texto):
    """Parsea la respuesta JSON de Gemini con limpieza de markdown."""
    if not texto:
        return None
    try:
        # Limpiar bloques de código markdown si vienen en la respuesta
        if "```" in texto:
            lines = texto.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            texto = "\n".join(lines)
        texto = texto.strip()
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


def _obtener_contexto_feedback(limite=10):
    """
    Obtiene los últimos N feedbacks del equipo para inyectarlos como
    contexto de aprendizaje al prompt de Gemini.
    """
    try:
        from tickets.models import FeedbackIA
        feedbacks = FeedbackIA.objects.select_related('ticket').order_by('-fecha')[:limite]
        if not feedbacks:
            return ""

        ejemplos = []
        for fb in feedbacks:
            if fb.ticket and fb.tipificacion_corregida:
                ejemplo = (
                    f"- Asunto: '{fb.ticket.asunto[:80]}' → "
                    f"Línea: {fb.linea_corregida}, "
                    f"Proceso: {fb.proceso_corregido}, "
                    f"Tipificación: {fb.tipificacion_corregida}, "
                    f"Criticidad: {fb.criticidad_corregida}"
                )
                if fb.observacion:
                    ejemplo += f" (Razón: {fb.observacion[:60]})"
                ejemplos.append(ejemplo)

        return "\n".join(ejemplos)
    except Exception:
        return ""


def analizar_ticket_con_ia(asunto, descripcion):
    """
    Análisis semántico con IA. Clasifica el ticket según la normativa BPE colombiana.
    Incorpora aprendizaje continuo basado en correcciones históricas del equipo.
    """
    # Obtener contexto de aprendizaje desde correcciones anteriores
    contexto_feedback = _obtener_contexto_feedback(limite=15)

    prompt = _construir_prompt_clasificacion(asunto, descripcion, contexto_feedback)
    texto = llamar_gemini(prompt)
    resultado = _parsear_respuesta_json(texto)

    if resultado:
        return {
            "linea": resultado.get("linea", "administrativo"),
            "proceso": resultado.get("proceso", "administrativa"),
            "tipificacion": resultado.get("tipificacion", "solicitud_cliente"),
            "criticidad": resultado.get("criticidad", "informativa"),
            "analisis_ia": resultado.get("analisis_ia", "Clasificado por UNIDOSSIS IA.")
        }

    # Fallback si la IA no responde
    return {
        "linea": "administrativo",
        "proceso": "administrativa",
        "tipificacion": "solicitud_cliente",
        "criticidad": "informativa",
        "analisis_ia": "Clasificación automática por fallback (sin conexión a IA)."
    }


def generar_resumen_cliente(asunto, cuerpo):
    """
    Genera un resumen completo orientado al cliente institucional.
    Extrae las oraciones más informativas del cuerpo, omitiendo saludos y cierres.
    Siempre retorna un string (nunca None). Intenta Gemini si hay cuota disponible.
    """
    import re

    # ── 1. Intentar con IA si está disponible ──────────────────────────────
    if API_URL:
        prompt = (
            "Eres un asistente de atención al cliente de Unidossis.\n"
            "Genera un RESUMEN COMPLETO pero conciso (máximo 3 oraciones, ≤350 caracteres) "
            "del siguiente caso PQRS. Captura el problema principal, cuándo ocurrió y qué se solicita.\n"
            "Usa lenguaje claro. NO empieces con saludos. NO uses jerga técnica interna.\n"
            "Devuelve SOLO el resumen, sin comillas ni prefijos.\n\n"
            f"Asunto: {asunto}\nDescripción: {cuerpo[:800]}"
        )
        try:
            texto = llamar_gemini(prompt, temperature=0.25)
            if texto:
                return texto.strip().replace('"', '').replace("'", '')[:380]
        except Exception:
            pass

    # ── 2. Extractive summarization local ────────────────────────────────
    # Patrones de líneas a OMITIR (saludos, cierres, datos aislados)
    OMITIR = re.compile(
        r'^('
        r'buenas\s+(tardes|noches|d[ií]as)|hola\b|cordial\s+saludo|estimad[ao]s?|'
        r'por\s+medio\s+del?\s+presente|a\s+quien\s+corresponda|señor|'
        r'de\s+manera\s+atenta|mediante\s+el\s+presente|apreciado|'
        r'agradezco|quedo\s+atenta?|cordialmente|atentamente|saludos|'
        r'sin\s+otro\s+particular|en\s+espera\s+de|esperamos\s+pronta|'
        r'gracias|adjunto|quedo\s+en\s+espera|para\s+mayor\s+informaci[oó]n|'
        r'\*+|\-+|_{3,}'
        r')',
        re.IGNORECASE
    )

    # Normalizar saltos de línea múltiples y limpiar
    texto = re.sub(r'\r\n|\r', '\n', cuerpo.strip())
    texto = re.sub(r'\n{3,}', '\n\n', texto)

    # Dividir por oraciones (punto/excl/interrogación seguido de espacio o salto)
    raw_oraciones = re.split(r'(?<=[.!?])\s+|\n+', texto)

    utiles = []
    chars = 0
    LIMITE = 370

    for o in raw_oraciones:
        o = o.strip().strip('"').strip("'")
        # Descartar cortas, saludos/cierres, urls
        if len(o) < 25:
            continue
        if OMITIR.match(o):
            continue
        if 'http' in o.lower() or re.match(r'^[\w\.-]+@', o):
            continue
        # Descartar líneas que sean solo números/fechas/datos de cabecera
        if re.match(r'^[\d\s:/\-,\.]+$', o):
            continue

        # Agregar oración si cabe dentro del límite
        espacio = len(o) + (2 if utiles else 0)
        if chars + espacio <= LIMITE:
            utiles.append(o)
            chars += espacio
        elif not utiles:
            # Al menos incluir el inicio de la primera oración útil
            utiles.append(o[:LIMITE - 3] + '…')
            break
        else:
            break

    if not utiles:
        # Fallback: tomar el inicio del cuerpo quitando saludo inicial
        limpio = OMITIR.sub('', texto).strip()
        return (limpio[:350] + '…') if len(limpio) > 350 else limpio

    resumen = ' '.join(utiles)
    if len(resumen) > 380:
        resumen = resumen[:377] + '…'
    return resumen


def reclasificar_ticket_con_ia(ticket):
    """
    Reclasifica un ticket existente usando el motor IA con aprendizaje.
    Retorna el resultado sin modificar el ticket (el agente decide si aplica).
    Útil para correos ingresados manualmente o tickets con clasificación incierta.
    """
    contexto_feedback = _obtener_contexto_feedback(limite=15)
    prompt = _construir_prompt_clasificacion(ticket.asunto, ticket.cuerpo, contexto_feedback)
    texto = llamar_gemini(prompt)
    resultado = _parsear_respuesta_json(texto)

    if resultado:
        return {
            "linea": resultado.get("linea", ticket.linea_servicio or "administrativo"),
            "proceso": resultado.get("proceso", ticket.proceso or "administrativa"),
            "tipificacion": resultado.get("tipificacion", ticket.tipificacion or "solicitud_cliente"),
            "criticidad": resultado.get("criticidad", ticket.criticidad or "informativa"),
            "analisis_ia": resultado.get("analisis_ia", "Reclasificado por UNIDOSSIS IA.")
        }
    return None


def analizar_correo_con_ia(asunto_correo, cuerpo_correo, remitente=""):
    """
    Analiza un correo entrante para determinar si es una PQRS válida
    y su clasificación sugerida.
    Devuelve dict con: es_pqrs (bool), tipo_solicitud, y clasificación completa.
    """
    contexto_feedback = _obtener_contexto_feedback(limite=15)

    prompt = f"""Eres UNIDOSSIS IA, experto en PQRS farmacéuticas para Unidossis Colombia.
Analiza el siguiente correo electrónico y determina:
1. Si es una PQRS válida (queja, reclamo, sugerencia, o solicitud de información)
2. Su clasificación completa según la normativa colombiana (Res. 1403, 0444, 2200)

{f"APRENDIZAJE DE CORRECCIONES ANTERIORES: {contexto_feedback}" if contexto_feedback else ""}

CORREO A ANALIZAR:
  Remitente: {remitente}
  Asunto: {asunto_correo}
  Cuerpo: {cuerpo_correo[:1500]}

Devuelve SOLO un JSON válido:
{{
  "es_pqrs": true/false,
  "tipo_solicitud": "<uno de: queja, reclamo, sugerencia, pregunta, felicitacion>",
  "linea": "<línea de servicio>",
  "proceso": "<área/proceso>",
  "tipificacion": "<tipificación específica>",
  "criticidad": "<nivel de criticidad>",
  "analisis_ia": "<Resumen del análisis en 2-3 oraciones>",
  "razon_no_pqrs": "<Solo si es_pqrs es false, explica brevemente por qué no es una PQRS>"
}}
"""

    texto = llamar_gemini(prompt, temperature=0.05)
    resultado = _parsear_respuesta_json(texto)

    if resultado:
        return {
            "es_pqrs": resultado.get("es_pqrs", True),
            "tipo_solicitud": resultado.get("tipo_solicitud", "queja"),
            "linea": resultado.get("linea", "administrativo"),
            "proceso": resultado.get("proceso", "administrativa"),
            "tipificacion": resultado.get("tipificacion", "solicitud_cliente"),
            "criticidad": resultado.get("criticidad", "informativa"),
            "analisis_ia": resultado.get("analisis_ia", "Analizado por UNIDOSSIS IA."),
            "razon_no_pqrs": resultado.get("razon_no_pqrs", "")
        }

    return {
        "es_pqrs": True,
        "tipo_solicitud": "queja",
        "linea": "administrativo",
        "proceso": "administrativa",
        "tipificacion": "solicitud_cliente",
        "criticidad": "informativa",
        "analisis_ia": "Clasificación por fallback (sin conexión a IA).",
        "razon_no_pqrs": ""
    }


def conversar_con_analista_ia(pregunta, contexto_tickets):
    """
    Chat UNIDOSSIS IA con mapeo de datos y mayor precision.
    """
    # Mapeo de terminos para que la IA entienda los codigos de la DB
    mapeo_contexto = """
    GUIA DE CODIGOS DE BASE DE DATOS:
    - Regionales: 'marly' (Bogotá Marly), 'occidente' (Regional Occidente), 'antioquia' (Regional Antioquia), 'costa' (Costa), 'llanos' (Llanos), 'eje_cafetero' (Eje Cafetero), 'liquidos' (Cundinamarca Líquidos), 'solidos' (Sólidos).
    - Estados: 'abierto' (Pendiente), 'revision' (En Gestión), 'resuelto' (Cerrado Éxito), 'cancelado' (Cerrado/Spam).
    - Criticidad: 'critica' (Grave/Res 0444), 'mayor' (Importante), 'menor' (Leve), 'informativa' (Informativa).
    - Procesos: 'gerencia', 'produccion', 'comercial', 'logistica', 'administrativa', 'talento', 'sst', 'calidad'.
    - Líneas: 'esteriles', 'oncologia', 'npt', 'magistral', 'solidos', 'dosis_anticipada', 'administrativo'.
    """

    # Enviar hasta 2000 tickets (Gemini 2.5 tiene ventana gigante, asi que cubrimos todo)
    resumen_tickets = json.dumps(contexto_tickets[:2000], ensure_ascii=False, default=str)

    system_prompt = f"""Tu nombre es UNIDOSSIS IA, asistente experto de Unidossis (Farmaceutica Colombiana).
    
    {mapeo_contexto}

    REGLAS DE ORO:
    1. ANALIZA PRIMERO: Antes de responder, revisa el JSON de tickets para dar cifras EXACTAS.
    2. SI NO SABES, NO INVENTES: Si te preguntan por algo que no esta en los datos (ej: ventas), indica que solo tienes acceso a PQRS.
    3. TONO: Profesional, amigable y experto en normativa (Res. 1403, 0444, 2200).
    4. CAPA: Si ves que un problema se repite (ej: muchas quejas de 'cadena de frio'), sugiere un CAPA (Accion Correctiva/Preventiva).

    CONTEO ACTUAL DE TICKETS (CONTEXTO):
    {resumen_tickets}

    PREGUNTA DEL USUARIO:
    {pregunta}

    INSTRUCCIONES DE RESPUESTA:
    - Responde en español.
    - Usa **negritas**.
    - Maximo 250 palabras.
    - Si te piden conteos, calcula los numeros REALES del JSON proporcionado.
    - Inicia con un saludo amable."""

    respuesta = llamar_gemini(system_prompt, temperature=0.1)
    if respuesta:
        return respuesta

    # Fallback local basico
    pregunta_min = pregunta.lower()
    total = len(contexto_tickets)
    if "cuanto" in pregunta_min or "conteo" in pregunta_min:
        return f"¡Hola! He analizado tu dashboard y encontre un total de **{total} tickets** registrados. Para un analisis detallado, por favor intenta en unos minutos cuando la conexion se estabilice."

    return f"¡Hola! Soy **UNIDOSSIS IA**. Actualmente estoy experimentando una alta demanda, pero puedo decirte que hay **{total} tickets** en el sistema. ¿En que mas puedo apoyarte?"
