from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db.models import Q, Count, Avg
from django.utils import timezone
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from functools import wraps
import json

from ..models import (
    Ticket, ArchivoAdjunto, Cliente, Ciudad, Cargo, MaestroInstitucion,
    PerfilUsuario, ConfiguracionSLA, AlertaSLA, LogActividad,
    ComentarioTicket, EncuestaSatisfaccion, FeedbackIA, IntentoLogin,
    SolicitudResetPassword
)
from ..ia_engine import analizar_ticket_con_ia, conversar_con_analista_ia, reclasificar_ticket_con_ia, generar_resumen_cliente

def custom_404(request, exception):
    """Handler personalizado para errores 404."""
    return render(request, '404.html', status=404)


def custom_500(request):
    """Handler personalizado para errores 500."""
    return render(request, '500.html', status=500)


def rol_requerido(*roles):
    """Decorador para restringir el acceso a vistas basado en el rol del PerfilUsuario."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if not hasattr(request.user, 'perfil'):
                return render(request, 'tickets/acceso_denegado.html', {
                    'mensaje': 'Su usuario no tiene un perfil configurado. Contacte al administrador.'
                }, status=403)

            # Si hay simulación activa, el usuario real es superadmin → permitir siempre
            if getattr(request, 'simulacion_activa', False):
                return view_func(request, *args, **kwargs)

            if request.user.perfil.rol not in roles and 'superadmin' not in [request.user.perfil.rol]:
                return render(request, 'tickets/acceso_denegado.html', {
                    'mensaje': f'El rol {request.user.perfil.get_rol_display()} no tiene permisos para esta sección.'
                }, status=403)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def _render_email_html(template_name, context):
    """Renderiza una plantilla HTML de email. Retorna None si falla."""
    try:
        from django.template.loader import render_to_string
        return render_to_string(template_name, context)
    except Exception:
        return None


def _enviar_acuse_recibo(ticket, request=None):
    """Envía acuse de recibo al cliente con plantilla HTML premium."""
    try:
        subject = f'Recibimos su PQRS — Caso #{ticket.ticket_id} | Unidossis'
        plain_text = (
            f'Estimado/a {ticket.remitente_nombre or "Cliente"},\n\n'
            f'Confirmamos que hemos recibido correctamente su solicitud.\n\n'
            f'  Número de caso: {ticket.ticket_id}\n'
            f'  Tipo de solicitud: {ticket.get_tipo_solicitud_display()}\n'
            f'  Asunto: {ticket.asunto}\n'
            f'  Fecha de ingreso: {ticket.fecha_ingreso.strftime("%d/%m/%Y %H:%M")}\n\n'
            f'Nuestro equipo revisará su caso y le dará respuesta en los tiempos establecidos.\n\n'
            f'Gracias por comunicarse con Unidossis.\n'
            f'servicio.cliente@unidossis.com.co'
        )
        html_message = _render_email_html('tickets/emails/acuse_recibo.html', {
            'nombre_cliente': ticket.remitente_nombre or 'Cliente',
            'ticket_id': ticket.ticket_id,
            'tipo_solicitud': ticket.get_tipo_solicitud_display(),
            'asunto': ticket.asunto,
            'fecha_ingreso': ticket.fecha_ingreso.strftime('%d/%m/%Y %H:%M'),
        })
        send_mail(
            subject=subject,
            message=plain_text,
            from_email='Servicio al cliente Unidossis <servicio.cliente@unidossis.com.co>',
            recipient_list=[ticket.remitente_email],
            html_message=html_message,
            fail_silently=True,
        )
        ticket.auto_respuesta_enviada = True
        ticket.save(update_fields=['auto_respuesta_enviada'])
        LogActividad.objects.create(
            ticket=ticket, usuario=None,
            accion='Acuse de recibo HTML enviado automáticamente al cliente',
            detalle=f'Correo enviado a: {ticket.remitente_email}'
        )
    except Exception:
        pass


def _enviar_respuesta_formal_y_csat(ticket, request=None):
    """
    Envía la respuesta formal al cierre con plantilla HTML premium e incluye
    enlace a encuesta CSAT. Crea el registro de encuesta con token único.
    """
    try:
        encuesta, created = EncuestaSatisfaccion.objects.get_or_create(ticket=ticket)
        base_url = request.build_absolute_uri('/')[:-1] if request else 'https://pqrs.unidossis.com.co'
        url_encuesta = f'{base_url}/encuesta/{encuesta.token}/'

        subject = f'Respuesta a su PQRS #{ticket.ticket_id} — Unidossis'
        plain_text = (
            f'Estimado/a {ticket.remitente_nombre or "Cliente"},\n\n'
            f'Hemos dado respuesta a su solicitud PQRS:\n\n'
            f'  Número de caso: {ticket.ticket_id}\n'
            f'  Asunto: {ticket.asunto}\n\n'
            f'RESPUESTA OFICIAL:\n'
            f'{ticket.respuesta_oficial or "Ver respuesta en el portal de clientes."}\n\n'
            f'Encuesta de satisfacción: {url_encuesta}\n\n'
            f'Gracias por su confianza en Unidossis.\n'
            f'servicio.cliente@unidossis.com.co'
        )
        html_message = _render_email_html('tickets/emails/respuesta_formal.html', {
            'nombre_cliente': ticket.remitente_nombre or 'Cliente',
            'ticket_id': ticket.ticket_id,
            'asunto': ticket.asunto,
            'respuesta_oficial': ticket.respuesta_oficial or 'Ver respuesta en el portal de clientes.',
            'url_encuesta': url_encuesta,
        })
        send_mail(
            subject=subject,
            message=plain_text,
            from_email='Servicio al cliente Unidossis <servicio.cliente@unidossis.com.co>',
            recipient_list=[ticket.remitente_email],
            html_message=html_message,
            fail_silently=False,
        )
        ticket.respuesta_formal_enviada = True
        ticket.save(update_fields=['respuesta_formal_enviada'])
        LogActividad.objects.create(
            ticket=ticket, usuario=request.user if request else None,
            accion='Respuesta formal HTML enviada al cliente con encuesta CSAT',
            detalle=f'URL encuesta: {url_encuesta}'
        )
    except Exception:
        pass




def _get_client_ip(request):
    """Obtiene la IP real del cliente (soporta proxies)."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


