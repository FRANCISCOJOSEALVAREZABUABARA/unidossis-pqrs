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
@rol_requerido('cliente')
def public_pqrs_view(request):
    # ── Si hay simulación activa de cliente, usar el mock del middleware ──
    if getattr(request, 'simulacion_activa', False) and getattr(request, 'cliente_simulado', None):
        perfil_cliente = request.cliente_simulado
    else:
        perfil_cliente = getattr(request.user, 'cliente_perfil', None)

    simulacion_activa = getattr(request, 'simulacion_activa', False)

    if perfil_cliente and not perfil_cliente.activo and not simulacion_activa:
        return render(request, 'tickets/acceso_denegado.html', {
            'mensaje': 'Su cuenta institucional se encuentra inactiva. Comuníquese con el equipo de Unidossis para más información.'
        }, status=403)

    ctx_base = {
        'TIPO_CHOICES': Ticket.TIPO_SOLICITUD_CHOICES,
        'perfil_cliente': perfil_cliente,
        'simulacion_activa': simulacion_activa,
        'rol_simulado': getattr(request, 'rol_simulado', None),
    }

    if request.method == 'POST':
        institucion = request.POST.get('institucion')
        entidad = institucion
        ciudad = request.POST.get('ciudad')
        nombre = request.POST.get('nombre')
        cargo = request.POST.get('cargo')
        telefono = request.POST.get('telefono')
        email = request.POST.get('email')
        tipo = request.POST.get('tipo_solicitud')
        asunto = request.POST.get('asunto')
        descripcion = request.POST.get('descripcion')

        if not (institucion and nombre and email and asunto and descripcion):
            ctx_base['error'] = 'Por favor, complete todos los campos obligatorios (Institución, Nombre, Correo, Asunto y Descripción).'
            return render(request, 'tickets/portal_form.html', ctx_base)

        # En simulación no se crea ticket real, solo se muestra éxito
        if simulacion_activa:
            from types import SimpleNamespace
            ticket_fake = SimpleNamespace(
                ticket_id='SIM-PREVIEW',
                remitente_email=email,
                asunto=asunto,
            )
            return render(request, 'tickets/portal_success.html', {
                'ticket': ticket_fake,
                'simulacion_activa': True,
            })

        # Procesamiento por IA
        analisis = analizar_ticket_con_ia(asunto, descripcion)

        nuevo_ticket = Ticket.objects.create(
            cliente_rel=perfil_cliente,
            entidad_cliente=entidad,
            institucion=institucion,
            ciudad=ciudad,
            remitente_nombre=nombre,
            solicitante_cargo=cargo,
            telefono=telefono,
            remitente_email=email,
            tipo_solicitud=tipo,
            asunto=asunto,
            cuerpo=descripcion,
            regional=perfil_cliente.regional if (perfil_cliente and perfil_cliente.regional) else 'liquidos',
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
            accion='Ticket creado por el cliente desde el portal',
            detalle=f'Clasificado por IA: {analisis["tipificacion"]} / {analisis["criticidad"]}'
        )

        return render(request, 'tickets/portal_success.html', {'ticket': nuevo_ticket})

    return render(request, 'tickets/portal_form.html', ctx_base)


@login_required
@rol_requerido('cliente')
def portal_cliente_dashboard(request):
    """Dashboard para que el cliente vea sus propios tickets."""
    from django.db.models import Count
    from django.utils import timezone
    import json as _json

    perfil = request.user.perfil

    # ── En modo simulación, usar el cliente inyectado por el middleware ──
    simulacion_activa = getattr(request, 'simulacion_activa', False)
    if simulacion_activa and getattr(request, 'cliente_simulado', None):
        cliente = request.cliente_simulado
    else:
        cliente = perfil.cliente

    if not cliente:
        return render(request, 'tickets/acceso_denegado.html', {
            'mensaje': 'Su usuario no está vinculado a ninguna institución clínica.'
        })

    tickets_qs = Ticket.objects.filter(cliente_rel=cliente).order_by('-fecha_ingreso')

    # ── KPIs principales ──
    total_tickets       = tickets_qs.count()
    tickets_resueltos   = tickets_qs.filter(estado='resuelto').count()
    tickets_cancelados  = tickets_qs.filter(estado='cancelado').count()
    tickets_en_proceso  = tickets_qs.exclude(estado__in=['resuelto', 'cancelado']).count()

    # Vencidos SLA: abiertos con más de 14 días
    limite_sla = timezone.now() - timezone.timedelta(days=14)
    tickets_vencidos_sla = tickets_qs.exclude(
        estado__in=['resuelto', 'cancelado']
    ).filter(fecha_ingreso__lt=limite_sla).count()

    pct_cumplimiento = round((tickets_resueltos / total_tickets * 100), 1) if total_tickets else 0
    pct_en_proceso   = round((tickets_en_proceso / total_tickets * 100), 1) if total_tickets else 0

    # ── Por Tipo de Solicitud ──
    tipo_labels_map = dict(Ticket.TIPO_SOLICITUD_CHOICES)
    por_tipo_qs = (
        tickets_qs.values('tipo_solicitud')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )
    por_tipo = [
        {'key': r['tipo_solicitud'], 'label': tipo_labels_map.get(r['tipo_solicitud'], r['tipo_solicitud']), 'cnt': r['cnt']}
        for r in por_tipo_qs
    ]

    # ── Por Línea de Servicio (Top 6) ──
    linea_labels_map = dict(Ticket.LINEA_CHOICES)
    por_linea_qs = (
        tickets_qs.exclude(linea_servicio__isnull=True)
        .values('linea_servicio')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')[:6]
    )
    por_linea = [
        {'key': r['linea_servicio'], 'label': linea_labels_map.get(r['linea_servicio'], r['linea_servicio']), 'cnt': r['cnt']}
        for r in por_linea_qs
    ]

    # ── Por Criticidad ──
    crit_labels_map = {'critica': 'Crítica', 'mayor': 'Mayor', 'menor': 'Menor', 'informativa': 'Informativa'}
    crit_colors = {'critica': '#ef4444', 'mayor': '#f97316', 'menor': '#eab308', 'informativa': '#22c55e'}
    por_criticidad_qs = (
        tickets_qs.exclude(criticidad__isnull=True)
        .values('criticidad')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )
    por_criticidad = [
        {'key': r['criticidad'], 'label': crit_labels_map.get(r['criticidad'], r['criticidad']),
         'cnt': r['cnt'], 'color': crit_colors.get(r['criticidad'], '#6366f1')}
        for r in por_criticidad_qs
    ]

    # ── Tendencia mensual (últimos 6 meses) ──
    hoy = timezone.now()
    tendencia = []
    for i in range(5, -1, -1):
        mes_inicio = (hoy - timezone.timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mes_fin = (mes_inicio + timezone.timedelta(days=32)).replace(day=1)
        cnt = tickets_qs.filter(fecha_ingreso__gte=mes_inicio, fecha_ingreso__lt=mes_fin).count()
        tendencia.append({'mes': mes_inicio.strftime('%b %Y'), 'cnt': cnt})

    # ── Serializar datos para Chart.js ──
    chart_tipo   = _json.dumps({'labels': [t['label'] for t in por_tipo],   'data': [t['cnt'] for t in por_tipo]})
    chart_linea  = _json.dumps({'labels': [l['label'] for l in por_linea],  'data': [l['cnt'] for l in por_linea]})
    chart_trend  = _json.dumps({'labels': [t['mes'] for t in tendencia],    'data': [t['cnt'] for t in tendencia]})

    # ── Últimos 8 tickets para tabla ──
    tickets_recientes = list(tickets_qs[:8])

    # ── Lazy backfill de resumen IA (máx 5 por carga, corre siempre) ──
    sin_resumen = [t for t in tickets_recientes if not t.resumen_cliente_ia and t.cuerpo][:5]
    for t in sin_resumen:
        try:
            resumen = generar_resumen_cliente(t.asunto, t.cuerpo)
            if resumen:
                Ticket.objects.filter(pk=t.pk).update(resumen_cliente_ia=resumen)
                t.resumen_cliente_ia = resumen
        except Exception:
            pass

    return render(request, 'tickets/cliente/dashboard.html', {
        'cliente': cliente,
        'tickets': tickets_recientes,
        'tickets_todos': tickets_qs,
        # KPIs
        'total_tickets': total_tickets,
        'tickets_resueltos': tickets_resueltos,
        'tickets_en_proceso': tickets_en_proceso,
        'tickets_cancelados': tickets_cancelados,
        'tickets_vencidos_sla': tickets_vencidos_sla,
        'pct_cumplimiento': pct_cumplimiento,
        'pct_en_proceso': pct_en_proceso,
        # Analytics
        'por_tipo': por_tipo,
        'por_linea': por_linea,
        'por_criticidad': por_criticidad,
        # Charts JSON
        'chart_tipo': chart_tipo,
        'chart_linea': chart_linea,
        'chart_trend': chart_trend,
        # Nav
        'nav_active': 'mis_pqrs',
        'simulacion_activa': simulacion_activa,
        'rol_simulado': getattr(request, 'rol_simulado', None),
    })


@login_required
@rol_requerido('cliente')
def portal_cliente_analytics(request):
    """Página de analíticas e indicadores para el portal cliente."""
    from django.db.models import Count
    from django.utils import timezone
    import json as _json

    perfil = request.user.perfil
    simulacion_activa = getattr(request, 'simulacion_activa', False)
    if simulacion_activa and getattr(request, 'cliente_simulado', None):
        cliente = request.cliente_simulado
    else:
        cliente = perfil.cliente

    if not cliente:
        return render(request, 'tickets/acceso_denegado.html', {
            'mensaje': 'Su usuario no está vinculado a ninguna institución clínica.'
        })

    tickets_qs = Ticket.objects.filter(cliente_rel=cliente)
    total_tickets = tickets_qs.count()
    tickets_resueltos = tickets_qs.filter(estado='resuelto').count()
    pct_cumplimiento = round((tickets_resueltos / total_tickets * 100), 1) if total_tickets else 0

    # Por Tipo
    tipo_labels_map = dict(Ticket.TIPO_SOLICITUD_CHOICES)
    por_tipo = [
        {'label': tipo_labels_map.get(r['tipo_solicitud'], r['tipo_solicitud']), 'cnt': r['cnt']}
        for r in tickets_qs.values('tipo_solicitud').annotate(cnt=Count('id')).order_by('-cnt')
    ]

    # Por Línea (Top 6)
    linea_labels_map = dict(Ticket.LINEA_CHOICES)
    por_linea = [
        {'label': linea_labels_map.get(r['linea_servicio'], r['linea_servicio']), 'cnt': r['cnt']}
        for r in tickets_qs.exclude(linea_servicio__isnull=True)
            .values('linea_servicio').annotate(cnt=Count('id')).order_by('-cnt')[:6]
    ]

    # Por Criticidad
    crit_labels_map = {'critica': 'Crítica', 'mayor': 'Mayor', 'menor': 'Menor', 'informativa': 'Informativa'}
    crit_colors = {'critica': '#ef4444', 'mayor': '#f97316', 'menor': '#eab308', 'informativa': '#22c55e'}
    por_criticidad = [
        {'label': crit_labels_map.get(r['criticidad'], r['criticidad']),
         'cnt': r['cnt'], 'color': crit_colors.get(r['criticidad'], '#6366f1')}
        for r in tickets_qs.exclude(criticidad__isnull=True)
            .values('criticidad').annotate(cnt=Count('id')).order_by('-cnt')
    ]

    # Por Estado
    estado_labels = {'abierto': 'Abierto', 'revision': 'En Revisión', 'resuelto': 'Resuelto', 'cancelado': 'Cancelado'}
    por_estado = [
        {'label': estado_labels.get(r['estado'], r['estado']), 'cnt': r['cnt']}
        for r in tickets_qs.values('estado').annotate(cnt=Count('id')).order_by('-cnt')
    ]

    # Tendencia mensual (6 meses)
    hoy = timezone.now()
    tendencia = []
    for i in range(5, -1, -1):
        mes_inicio = (hoy - timezone.timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mes_fin = (mes_inicio + timezone.timedelta(days=32)).replace(day=1)
        cnt = tickets_qs.filter(fecha_ingreso__gte=mes_inicio, fecha_ingreso__lt=mes_fin).count()
        tendencia.append({'mes': mes_inicio.strftime('%b %Y'), 'cnt': cnt})

    chart_tipo   = _json.dumps({'labels': [t['label'] for t in por_tipo],  'data': [t['cnt'] for t in por_tipo]})
    chart_linea  = _json.dumps({'labels': [l['label'] for l in por_linea], 'data': [l['cnt'] for l in por_linea]})
    chart_trend  = _json.dumps({'labels': [t['mes'] for t in tendencia],   'data': [t['cnt'] for t in tendencia]})
    chart_estado = _json.dumps({'labels': [e['label'] for e in por_estado],'data': [e['cnt'] for e in por_estado]})

    return render(request, 'tickets/cliente/analytics.html', {
        'cliente': cliente,
        'total_tickets': total_tickets,
        'tickets_resueltos': tickets_resueltos,
        'pct_cumplimiento': pct_cumplimiento,
        'por_tipo': por_tipo,
        'por_linea': por_linea,
        'por_criticidad': por_criticidad,
        'por_estado': por_estado,
        'chart_tipo': chart_tipo,
        'chart_linea': chart_linea,
        'chart_trend': chart_trend,
        'chart_estado': chart_estado,
        'nav_active': 'analiticas',
        'simulacion_activa': simulacion_activa,
        'rol_simulado': getattr(request, 'rol_simulado', None),
    })


