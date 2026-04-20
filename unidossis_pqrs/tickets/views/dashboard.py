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
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'agente')
def dashboard_view(request):
    perfil = request.user.perfil

    # Base query según rol
    if perfil.rol in ['superadmin', 'admin_pqrs', 'agente']:
        tickets_query = Ticket.objects.all()
    elif perfil.rol == 'director_regional':
        # En simulación: si no se eligió regional específica, mostrar todos (modo preview)
        if perfil.regional:
            tickets_query = Ticket.objects.filter(regional=perfil.regional)
        else:
            tickets_query = Ticket.objects.all()
    else:
        # Fallback seguro para cualquier otro rol o estado inesperado
        tickets_query = Ticket.objects.all()

    # Filtro por cliente (Para Inteligencia Analítica y buscador inteligente)
    cliente_id = request.GET.get('cliente_id')
    cliente_filtrado_nombre = None
    if cliente_id:
        tickets_query = tickets_query.filter(cliente_rel_id=cliente_id)
        try:
            cliente_filtrado_nombre = Cliente.objects.get(id=cliente_id).nombre
        except Cliente.DoesNotExist:
            cliente_filtrado_nombre = None

    # Motor de búsqueda
    search_query = request.GET.get('q')
    if search_query:
        tickets_query = tickets_query.filter(
            Q(ticket_id__icontains=search_query) |
            Q(asunto__icontains=search_query) |
            Q(remitente_nombre__icontains=search_query) |
            Q(remitente_email__icontains=search_query) |
            Q(entidad_cliente__icontains=search_query) |
            Q(institucion__icontains=search_query) |
            Q(responsable__icontains=search_query) |
            Q(cuerpo__icontains=search_query) |
            Q(cliente_rel__nombre__icontains=search_query)
        )

    # Obtener IDs de clientes que tienen tickets en esta consulta (rol + búsqueda + filtro actual, sin estado)
    clientes_con_tickets_ids = list(tickets_query.exclude(cliente_rel__isnull=True).values_list('cliente_rel_id', flat=True).distinct())

    # Estadísticas generales y totales de las pestañas (Calculados ANTES de aplicar el filtro de estado)
    total_tickets = tickets_query.count()
    total_abiertos = tickets_query.exclude(estado__in=['resuelto', 'cancelado']).count()
    total_cerrados = tickets_query.filter(estado='resuelto').count()
    total_revision = tickets_query.filter(estado='revision').count()
    total_cancelados = tickets_query.filter(estado='cancelado').count()
    cumplimiento = round((total_cerrados / total_tickets * 100), 1) if total_tickets > 0 else 0

    # SLA semáforo
    tickets_abiertos = list(tickets_query.exclude(estado__in=['resuelto', 'cancelado']))
    vencidas = sum(1 for t in tickets_abiertos if t.estado_sla() == 'vencido')
    peligro = sum(1 for t in tickets_abiertos if t.estado_sla() == 'peligro')
    bien = sum(1 for t in tickets_abiertos if t.estado_sla() == 'bien')

    # SLA health %
    total_activos_sla = vencidas + peligro + bien
    sla_health = round((bien / total_activos_sla * 100)) if total_activos_sla > 0 else 100

    # Tickets de hoy
    from datetime import timedelta
    hoy = timezone.now().date()
    # Compatibilidad con SQLite (datetime)
    tickets_hoy = sum(1 for t in tickets_query if t.fecha_ingreso.date() == hoy)

    # APLICAR EL FILTRO DE ESTADO A LA TABLA PRINCIPAL (Al final)
    filtro_estado = request.GET.get('estado')
    if filtro_estado:
        tickets_query = tickets_query.filter(estado=filtro_estado)

    # Paginación para la tabla
    paginator = Paginator(tickets_query.order_by('-fecha_ingreso'), 30)
    from django.db.models import Count
    regional_dict = dict(Ticket.REGIONAL_CHOICES)
    linea_dict = dict(Ticket.LINEA_CHOICES)

    top_regionales = list(tickets_query.exclude(regional__isnull=True).exclude(regional='').values('regional').annotate(
        total=Count('id')
    ).order_by('-total')[:4])

    for r in top_regionales:
        r['nombre'] = regional_dict.get(r['regional'], r['regional'])
        r['porcentaje'] = round((r['total'] / total_tickets * 100)) if total_tickets > 0 else 0
        r['abiertos'] = tickets_query.filter(regional=r['regional']).exclude(estado__in=['resuelto', 'cancelado']).count()

    top_lineas = list(tickets_query.exclude(linea_servicio__isnull=True).exclude(linea_servicio='').values('linea_servicio').annotate(
        total=Count('id')
    ).order_by('-total')[:4])

    for l in top_lineas:
        l['nombre'] = linea_dict.get(l['linea_servicio'], l['linea_servicio'])
        l['porcentaje'] = round((l['total'] / total_tickets * 100)) if total_tickets > 0 else 0

    clientes_disponibles = Cliente.objects.filter(id__in=clientes_con_tickets_ids, activo=True).order_by('nombre')

    context = {
        'tickets': tickets_query.order_by('-fecha_ingreso'),
        'cantidad_total': total_tickets,
        'cantidad_urgentes': total_abiertos,
        'total_cerrados': total_cerrados,
        'total_revision': total_revision,
        'total_cancelados': total_cancelados,
        'cumplimiento': cumplimiento,
        'vencidas': vencidas,
        'peligro': peligro,
        'bien': bien,
        'sla_health': sla_health,
        'tickets_hoy': tickets_hoy,
        'top_regionales': top_regionales,
        'top_lineas': top_lineas,
        'filtro_actual': filtro_estado,
        'perfil': perfil,
        'nav_active': 'dashboard',
        'clientes_disponibles': clientes_disponibles,
        'cliente_id_selected': cliente_id,
        'cliente_filtrado_nombre': cliente_filtrado_nombre,
        # Choices para modal de creación manual
        'TIPO_CHOICES': Ticket.TIPO_SOLICITUD_CHOICES,
        'REGIONAL_CHOICES': Ticket.REGIONAL_CHOICES,
    }

    # ─── Indicadores CSAT ─────────────────────────────────────
    encuestas_respondidas = EncuestaSatisfaccion.objects.filter(
        ticket__in=Ticket.objects.all() if perfil.rol in ['superadmin', 'admin_pqrs'] else tickets_query,
        puntuacion__isnull=False
    )
    total_encuestas_resp = encuestas_respondidas.count()
    csat_promedio = encuestas_respondidas.aggregate(avg=Avg('puntuacion'))['avg']
    csat_promedio = round(csat_promedio, 1) if csat_promedio else 0
    csat_satisfechos = encuestas_respondidas.filter(puntuacion__gte=3).count()
    csat_insatisfechos = encuestas_respondidas.filter(puntuacion__lt=3).count()
    csat_tasa = round((csat_satisfechos / total_encuestas_resp * 100), 1) if total_encuestas_resp > 0 else 0
    csat_pendientes = EncuestaSatisfaccion.objects.filter(
        ticket__in=Ticket.objects.all() if perfil.rol in ['superadmin', 'admin_pqrs'] else tickets_query,
        puntuacion__isnull=True
    ).exclude(estado='expirada').count()

    context['csat_promedio'] = csat_promedio
    context['csat_total_resp'] = total_encuestas_resp
    context['csat_satisfechos'] = csat_satisfechos
    context['csat_insatisfechos'] = csat_insatisfechos
    context['csat_tasa'] = csat_tasa
    context['csat_pendientes'] = csat_pendientes
    return render(request, 'tickets/dashboard.html', context)


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def crear_pqrs_manual_view(request):
    """Permite a superadmin y admin_pqrs crear una PQRS manualmente
    para casos recibidos por teléfono, presencial, etc."""
    if request.method != 'POST':
        return redirect('dashboard')

    institucion = request.POST.get('institucion', '')
    ciudad = request.POST.get('ciudad', '')
    nombre = request.POST.get('nombre', '')
    cargo = request.POST.get('cargo', '')
    telefono = request.POST.get('telefono', '')
    email = request.POST.get('email', '')
    tipo = request.POST.get('tipo_solicitud', 'queja')
    regional = request.POST.get('regional', '')
    asunto = request.POST.get('asunto', '')
    descripcion = request.POST.get('descripcion', '')
    medio_recepcion = request.POST.get('medio_recepcion', 'manual')

    if not (institucion and nombre and email and asunto and descripcion):
        from django.contrib import messages
        messages.error(request, 'Complete todos los campos obligatorios.')
        return redirect('dashboard')

    # Buscar cliente existente
    cliente_rel = Cliente.objects.filter(nombre__iexact=institucion).first()

    # Procesamiento por IA
    analisis = analizar_ticket_con_ia(asunto, descripcion)
    regional_asignada = regional if regional else (cliente_rel.regional if cliente_rel else analisis.get('regional', 'liquidos'))

    # Autocrear cliente si no existe
    if not cliente_rel:
        ciudad_obj = Ciudad.objects.filter(nombre__iexact=ciudad).first() if ciudad else None
        cliente_rel = Cliente.objects.create(
            nombre=institucion,
            regional=regional_asignada,
            ciudad=ciudad_obj,
            email_principal=email,
            activo=True
        )

    nuevo_ticket = Ticket.objects.create(
        cliente_rel=cliente_rel,
        entidad_cliente=institucion,
        institucion=institucion,
        ciudad=ciudad,
        remitente_nombre=nombre,
        solicitante_cargo=cargo,
        telefono=telefono,
        remitente_email=email,
        tipo_solicitud=tipo,
        asunto=asunto,
        cuerpo=descripcion,
        regional=regional_asignada,
        proceso=analisis['proceso'],
        linea_servicio=analisis['linea'],
        tipificacion=analisis['tipificacion'],
        criticidad=analisis['criticidad'],
        analisis_ia=analisis['analisis_ia'],
        clasificado_por_ia=True
    )

    # Archivos adjuntos
    if request.FILES.getlist('adjuntos'):
        for f in request.FILES.getlist('adjuntos'):
            ArchivoAdjunto.objects.create(ticket=nuevo_ticket, archivo=f)

    # Log de actividad
    LogActividad.objects.create(
        ticket=nuevo_ticket, usuario=request.user,
        accion=f'PQRS creada manualmente ({medio_recepcion})',
        detalle=f'Creado por {request.user.get_full_name() or request.user.username} | '
                f'Medio: {medio_recepcion} | IA: {analisis["tipificacion"]} / {analisis["criticidad"]}'
    )

    return redirect('ticket_detail', ticket_id=nuevo_ticket.ticket_id)


