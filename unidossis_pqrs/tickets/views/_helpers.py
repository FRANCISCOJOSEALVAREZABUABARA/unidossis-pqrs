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


def _enviar_acuse_recibo(ticket, request=None):
    """Envía acuse de recibo al cliente cuando se crea un ticket por email."""
    try:
        send_mail(
            subject=f'✅ Recibimos su PQRS — Caso #{ticket.ticket_id} | Unidossis',
            message=(
                f'Estimado/a {ticket.remitente_nombre or "Cliente"},\n\n'
                f'Confirmamos que hemos recibido correctamente su solicitud.\n\n'
                f'  • Número de caso: {ticket.ticket_id}\n'
                f'  • Tipo de solicitud: {ticket.get_tipo_solicitud_display()}\n'
                f'  • Asunto: {ticket.asunto}\n'
                f'  • Fecha de ingreso: {ticket.fecha_ingreso.strftime("%d/%m/%Y %H:%M")}\n\n'
                f'Nuestro equipo revisará su caso y le dará respuesta en los tiempos establecidos '
                f'según nuestra política de servicio.\n\n'
                f'Gracias por comunicarse con Unidossis.\n\n'
                f'— Servicio al Cliente UNIDOSSIS\n'
                f'  servicio.cliente@unidossis.com.co'
            ),
            from_email='Servicio al cliente Unidossis <servicio.cliente@unidossis.com.co>',
            recipient_list=[ticket.remitente_email],
            fail_silently=True,
        )
        ticket.auto_respuesta_enviada = True
        ticket.save(update_fields=['auto_respuesta_enviada'])
        LogActividad.objects.create(
            ticket=ticket, usuario=None,
            accion='Acuse de recibo enviado automáticamente al cliente',
            detalle=f'Correo enviado a: {ticket.remitente_email}'
        )
    except Exception:
        pass


def _enviar_respuesta_formal_y_csat(ticket, request=None):
    """
    Envía la respuesta formal al cierre e incluye enlace a encuesta CSAT.
    Crea el registro de encuesta con token único.
    """
    try:
        # Crear o recuperar encuesta CSAT
        encuesta, created = EncuestaSatisfaccion.objects.get_or_create(ticket=ticket)

        # Construir URL de la encuesta
        if request:
            base_url = request.build_absolute_uri('/')[:-1]
        else:
            base_url = 'https://pqrs.unidossis.com.co'

        url_encuesta = f'{base_url}/encuesta/{encuesta.token}/'

        mensaje = (
            f'Estimado/a {ticket.remitente_nombre or "Cliente"},\n\n'
            f'Nos complace informarle que hemos dado respuesta a su solicitud PQRS:\n\n'
            f'  • Número de caso: {ticket.ticket_id}\n'
            f'  • Asunto: {ticket.asunto}\n\n'
            f'RESPUESTA OFICIAL DE UNIDOSSIS:\n'
            f'{"─" * 50}\n'
            f'{ticket.respuesta_oficial or "Ver respuesta en el portal de clientes."}\n'
            f'{"─" * 50}\n\n'
            f'📊 ENCUESTA DE SATISFACCIÓN:\n'
            f'Por favor califique nuestra atención haciendo clic en el siguiente enlace:\n'
            f'{url_encuesta}\n\n'
            f'Su opinión es muy importante para nosotros y nos ayuda a mejorar continuamente.\n\n'
            f'Gracias por su confianza en Unidossis.\n\n'
            f'— Servicio al Cliente UNIDOSSIS\n'
            f'  servicio.cliente@unidossis.com.co'
        )

        send_mail(
            subject=f'📋 Respuesta a su PQRS #{ticket.ticket_id} — Unidossis',
            message=mensaje,
            from_email='Servicio al cliente Unidossis <servicio.cliente@unidossis.com.co>',
            recipient_list=[ticket.remitente_email],
            fail_silently=False,
        )
        ticket.respuesta_formal_enviada = True
        ticket.save(update_fields=['respuesta_formal_enviada'])
        LogActividad.objects.create(
            ticket=ticket, usuario=request.user if request else None,
            accion='Respuesta formal enviada al cliente con encuesta CSAT',
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


