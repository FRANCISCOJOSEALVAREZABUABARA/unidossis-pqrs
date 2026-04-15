"""
Módulo centralizado de notificaciones — Email + WhatsApp.
Envía notificaciones por ambos canales cuando están configurados.

Configuración requerida en settings.py o variables de entorno:
  - SMTP:     EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
  - WhatsApp: WHATSAPP_API_TOKEN, WHATSAPP_PHONE_ID
"""
import os
import json
import logging
import urllib.request
import urllib.error
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger('unidossis.notificaciones')


# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────

WHATSAPP_API_TOKEN = os.getenv('WHATSAPP_API_TOKEN', '')
WHATSAPP_PHONE_ID = os.getenv('WHATSAPP_PHONE_ID', '')
WHATSAPP_API_URL = f'https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages'


def _whatsapp_configurado():
    """Verifica si la API de WhatsApp está configurada."""
    return bool(WHATSAPP_API_TOKEN and WHATSAPP_PHONE_ID)


def _smtp_configurado():
    """Verifica si el SMTP real está configurado (no console backend)."""
    return 'console' not in getattr(settings, 'EMAIL_BACKEND', 'console')


# ─────────────────────────────────────────────────────────────
# ENVÍO WHATSAPP (Meta Cloud API)
# ─────────────────────────────────────────────────────────────

def enviar_whatsapp(telefono, mensaje):
    """
    Envía un mensaje de texto por WhatsApp usando la Meta Cloud API.
    El teléfono debe incluir código de país (ej: 573001234567).
    Retorna True si el envío fue exitoso.
    """
    if not _whatsapp_configurado():
        logger.info(f'[WhatsApp] No configurado. Mensaje para {telefono}: {mensaje[:50]}...')
        return False

    # Limpiar teléfono
    telefono_limpio = ''.join(c for c in telefono if c.isdigit())
    if not telefono_limpio:
        return False

    # Si no tiene código de país Colombia, agregarlo
    if len(telefono_limpio) == 10 and telefono_limpio.startswith('3'):
        telefono_limpio = '57' + telefono_limpio

    payload = json.dumps({
        'messaging_product': 'whatsapp',
        'to': telefono_limpio,
        'type': 'text',
        'text': {'body': mensaje}
    }).encode('utf-8')

    headers = {
        'Authorization': f'Bearer {WHATSAPP_API_TOKEN}',
        'Content-Type': 'application/json',
    }

    try:
        req = urllib.request.Request(WHATSAPP_API_URL, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f'[WhatsApp] ✅ Enviado a {telefono_limpio}')
                return True
            else:
                logger.warning(f'[WhatsApp] ⚠️ Status {response.status} para {telefono_limpio}')
                return False
    except urllib.error.HTTPError as e:
        logger.error(f'[WhatsApp] ❌ Error HTTP {e.code}: {e.read().decode()[:200]}')
        return False
    except Exception as e:
        logger.error(f'[WhatsApp] ❌ Error: {str(e)[:200]}')
        return False


# ─────────────────────────────────────────────────────────────
# ENVÍO EMAIL
# ─────────────────────────────────────────────────────────────

def enviar_email(destinatario, asunto, mensaje):
    """
    Envía un email al destinatario.
    En desarrollo usa console backend; en producción usa SMTP real.
    """
    try:
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Unidossis PQRS <soporte@unidossis.com.co>'),
            recipient_list=[destinatario],
            fail_silently=True,
        )
        logger.info(f'[Email] ✅ Enviado a {destinatario}: {asunto}')
        return True
    except Exception as e:
        logger.error(f'[Email] ❌ Error enviando a {destinatario}: {str(e)[:200]}')
        return False


# ─────────────────────────────────────────────────────────────
# NOTIFICACIONES DE ALTO NIVEL
# ─────────────────────────────────────────────────────────────

def notificar_acuse_recibo(ticket):
    """Envía acuse de recibo al cliente por email y WhatsApp."""
    mensaje = (
        f'✅ UNIDOSSIS — Recibimos su solicitud\n\n'
        f'Caso: {ticket.ticket_id}\n'
        f'Tipo: {ticket.get_tipo_solicitud_display()}\n'
        f'Asunto: {ticket.asunto[:100]}\n\n'
        f'Nuestro equipo revisará su caso y le dará respuesta '
        f'en los tiempos establecidos.\n\n'
        f'Gracias por comunicarse con Unidossis.'
    )

    # Email
    if ticket.remitente_email and '@' in ticket.remitente_email:
        enviar_email(
            ticket.remitente_email,
            f'✅ Recibimos su PQRS — Caso #{ticket.ticket_id} | Unidossis',
            mensaje
        )

    # WhatsApp
    telefono = getattr(ticket, 'telefono', '') or ''
    if telefono and telefono not in ('N/R', 'None', ''):
        enviar_whatsapp(telefono, mensaje)


def notificar_cambio_estado(ticket, estado_anterior):
    """Notifica al cliente cuando cambia el estado del ticket."""
    mensaje = (
        f'📋 UNIDOSSIS — Actualización de su caso\n\n'
        f'Caso: {ticket.ticket_id}\n'
        f'Estado anterior: {estado_anterior}\n'
        f'Nuevo estado: {ticket.get_estado_display()}\n\n'
        f'Si tiene preguntas, puede responder a este mensaje.'
    )

    if ticket.remitente_email and '@' in ticket.remitente_email:
        enviar_email(
            ticket.remitente_email,
            f'📋 Actualización PQRS #{ticket.ticket_id} | Unidossis',
            mensaje
        )

    telefono = getattr(ticket, 'telefono', '') or ''
    if telefono and telefono not in ('N/R', 'None', ''):
        enviar_whatsapp(telefono, mensaje)


def notificar_respuesta_formal(ticket, url_encuesta=''):
    """Notifica al cliente con la respuesta oficial y encuesta CSAT."""
    mensaje = (
        f'📋 UNIDOSSIS — Respuesta a su solicitud\n\n'
        f'Caso: {ticket.ticket_id}\n'
        f'Asunto: {ticket.asunto[:100]}\n\n'
        f'RESPUESTA:\n'
        f'{ticket.respuesta_oficial or "Ver respuesta en el portal."}\n\n'
    )

    if url_encuesta:
        mensaje += (
            f'📊 ENCUESTA:\n'
            f'Por favor califique nuestra atención:\n'
            f'{url_encuesta}\n\n'
        )

    mensaje += 'Gracias por su confianza en Unidossis.'

    if ticket.remitente_email and '@' in ticket.remitente_email:
        enviar_email(
            ticket.remitente_email,
            f'📋 Respuesta PQRS #{ticket.ticket_id} | Unidossis',
            mensaje
        )

    telefono = getattr(ticket, 'telefono', '') or ''
    if telefono and telefono not in ('N/R', 'None', ''):
        enviar_whatsapp(telefono, mensaje)


def notificar_alerta_sla(ticket, tipo_alerta, destinatarios_email):
    """
    Notifica sobre alertas SLA a los responsables internos.
    tipo_alerta: 'peligro' o 'vencido'
    destinatarios_email: lista de emails
    """
    if tipo_alerta == 'peligro':
        emoji = '⚠️'
        nivel = 'EN PELIGRO'
    else:
        emoji = '🔴'
        nivel = 'VENCIDO — ESCALAMIENTO'

    mensaje = (
        f'{emoji} ALERTA SLA — Ticket {nivel}\n\n'
        f'Caso: {ticket.ticket_id}\n'
        f'Asunto: {ticket.asunto[:100]}\n'
        f'Regional: {ticket.get_regional_display() if ticket.regional else "N/A"}\n'
        f'Responsable: {ticket.responsable or "Sin asignar"}\n'
        f'Días transcurridos: {ticket.dias_transcurridos()}\n\n'
        f'Acción requerida: Revise y responda este caso antes del vencimiento.'
    )

    for email in destinatarios_email:
        if email and '@' in email:
            enviar_email(
                email.strip(),
                f'{emoji} Alerta SLA {nivel} — #{ticket.ticket_id}',
                mensaje
            )


def estado_canales():
    """Retorna el estado de configuración de los canales de notificación."""
    return {
        'email': {
            'configurado': _smtp_configurado(),
            'backend': getattr(settings, 'EMAIL_BACKEND', 'no configurado'),
        },
        'whatsapp': {
            'configurado': _whatsapp_configurado(),
            'phone_id': WHATSAPP_PHONE_ID[:6] + '...' if WHATSAPP_PHONE_ID else 'no configurado',
        }
    }
