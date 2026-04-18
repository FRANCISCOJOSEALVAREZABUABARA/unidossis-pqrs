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
from ._helpers import rol_requerido, _get_client_ip, _enviar_acuse_recibo, _enviar_respuesta_formal_y_csat

@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'agente', 'cliente')
def ticket_detail_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    perfil = request.user.perfil

    # Calcular si el agente está asignado a este ticket (su nombre aparece en 'responsable')
    es_agente_asignado = False
    if perfil.rol == 'agente':
        responsable_str = (ticket.responsable or "").lower()
        nombre_usuario = request.user.get_full_name().lower() if request.user.get_full_name() else ""
        es_agente_asignado = (
            request.user.username.lower() in responsable_str or
            (nombre_usuario and nombre_usuario in responsable_str) or
            (request.user.last_name and request.user.last_name.lower() in responsable_str) or
            (request.user.first_name and request.user.first_name.lower() in responsable_str)
        )

    # Validaciones de seguridad por rol
    if perfil.rol == 'cliente':
        if ticket.cliente_rel != perfil.cliente:
            return redirect('acceso_denegado')
    elif perfil.rol == 'director_regional':
        if ticket.regional != perfil.regional:
            return redirect('acceso_denegado')

    adjuntos_cliente = ticket.archivos_adjuntos.filter(es_respuesta_agente=False, es_soporte_interno=False)
    adjuntos_unidossis = ticket.archivos_adjuntos.filter(es_respuesta_agente=True)
    adjuntos_internos = ticket.archivos_adjuntos.filter(es_soporte_interno=True)
    comentarios = ticket.comentarios.all()
    logs = ticket.logs.all()[:20]

    if request.method == 'POST' and perfil.rol != 'cliente':
        # Los agentes solo pueden hacer POST si están asignados al ticket
        if perfil.rol == 'agente' and not es_agente_asignado:
            return redirect('ticket_detail', ticket_id=ticket.ticket_id)
        estado_anterior = ticket.estado
        nuevo_estado = request.POST.get('nuevo_estado')
        respuesta_texto = request.POST.get('respuesta_oficial')

        if nuevo_estado in dict(Ticket.STATUS_CHOICES):
            ticket.estado = nuevo_estado

        proceso = request.POST.get('proceso')
        linea = request.POST.get('linea_servicio')
        tipificacion = request.POST.get('tipificacion')
        criticidad = request.POST.get('criticidad')
        regional = request.POST.get('regional')

        if proceso: ticket.proceso = proceso
        if linea: ticket.linea_servicio = linea
        if tipificacion: ticket.tipificacion = tipificacion
        if criticidad: ticket.criticidad = criticidad

        # Regional: superadmin, admin_pqrs y agentes asignados pueden cambiarla
        if regional is not None and perfil.rol in ('superadmin', 'admin_pqrs', 'agente'):
            regional_anterior = ticket.regional
            ticket.regional = regional
            if regional != regional_anterior:
                LogActividad.objects.create(
                    ticket=ticket, usuario=request.user,
                    accion=f'Regional cambiada: {regional_anterior or "N/A"} → {regional or "N/A"}',
                    detalle=f'Cambiado por: {request.user.get_full_name() or request.user.username}'
                )

        responsable_manual = request.POST.get('responsable')
        if responsable_manual: ticket.responsable = responsable_manual

        if respuesta_texto is not None and perfil.rol != 'agente':
            ticket.respuesta_oficial = respuesta_texto

        ticket.save()

        # Log de actividad automático
        if nuevo_estado and nuevo_estado != estado_anterior:
            LogActividad.objects.create(
                ticket=ticket, usuario=request.user,
                accion=f'Estado cambiado: {estado_anterior} → {nuevo_estado}',
                detalle=f'Cambiado por: {request.user.get_full_name() or request.user.username}'
            )

        # Archivos adjuntos del agente (respuesta al cliente)
        if request.FILES.getlist('archivos_agente'):
            for archivo_subido in request.FILES.getlist('archivos_agente'):
                ArchivoAdjunto.objects.create(
                    ticket=ticket,
                    archivo=archivo_subido,
                    es_respuesta_agente=True,
                    subido_por_sistema=False
                )

        # Soportes y evidencias internas (no visibles para el cliente)
        if request.FILES.getlist('soportes_internos'):
            for archivo_subido in request.FILES.getlist('soportes_internos'):
                ArchivoAdjunto.objects.create(
                    ticket=ticket,
                    archivo=archivo_subido,
                    es_soporte_interno=True,
                    subido_por_sistema=False
                )

        # Cerrar y enviar respuesta formal + CSAT (no permitido para agentes)
        if 'cerrar_y_enviar' in request.POST and perfil.rol != 'agente':
            ticket.estado = 'resuelto'
            ticket.save()
            _enviar_respuesta_formal_y_csat(ticket, request)

        return redirect('ticket_detail', ticket_id=ticket.ticket_id)

    template_name = 'tickets/detalle.html'
    if perfil.rol == 'cliente':
        template_name = 'tickets/cliente/detalle.html'

    return render(request, template_name, {
        'ticket': ticket,
        'adjuntos_cliente': adjuntos_cliente,
        'adjuntos_unidossis': adjuntos_unidossis,
        'adjuntos_internos': adjuntos_internos,
        'comentarios': comentarios,
        'logs': logs,
        'STATUS_CHOICES': Ticket.STATUS_CHOICES,
        'AREA_CHOICES': Ticket.AREA_CHOICES,
        'LINEA_CHOICES': Ticket.LINEA_CHOICES,
        'TIPIFICACION_CHOICES': Ticket.TIPIFICACION_CHOICES,
        'CRITICIDAD_CHOICES': Ticket.CRITICIDAD_CHOICES,
        'REGIONAL_CHOICES': Ticket.REGIONAL_CHOICES,
        'perfil': perfil,
        'nav_active': 'dashboard',
        'cliente': perfil.cliente if perfil.rol == 'cliente' else None,
        'es_agente_asignado': es_agente_asignado,  # Pasado al template para controlar edición
    })


