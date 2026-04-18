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
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional')
def api_chat_analitico(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        pregunta = data.get('message', '')
        tickets = Ticket.objects.all().values(
            'ticket_id', 'remitente_nombre', 'asunto', 'estado',
            'criticidad', 'regional', 'proceso', 'linea_servicio'
        )
        contexto = list(tickets)
        respuesta = conversar_con_analista_ia(pregunta, contexto)
        return JsonResponse({'reply': respuesta})
    return JsonResponse({'error': 'Método no permitido'}, status=405)


@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor')
def api_buscar_clientes(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 3:
        return JsonResponse({'results': []})
    resultados = Cliente.objects.filter(nombre__icontains=query, activo=True).select_related('ciudad')[:15]
    data = [{
        'nombre': c.nombre,
        'regional': c.regional or '',
        'ciudad': c.ciudad.nombre if c.ciudad else '',
        'email': c.email_principal or '',
    } for c in resultados]
    return JsonResponse({'results': data})


@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor')
def api_buscar_ciudades(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 3:
        return JsonResponse({'results': []})
    resultados = Ciudad.objects.filter(nombre__icontains=query)[:15]
    data = [{'id': c.id, 'nombre': c.nombre} for c in resultados]
    return JsonResponse({'results': data})


@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor')
def api_buscar_cargos(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    resultados = Cargo.objects.filter(nombre__icontains=query)[:10]
    data = [{'nombre': c.nombre} for c in resultados]
    return JsonResponse({'results': data})


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_buscar_clientes_admin(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    resultados = Cliente.objects.filter(nombre__icontains=query, user__isnull=True)[:15]
    data = [{'id': c.id, 'nombre': c.nombre, 'regional': c.regional,
             'email': c.email_principal, 'emails_adicionales': c.emails_adicionales or ""}
            for c in resultados]
    return JsonResponse({'results': data})


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_buscar_maestro_instituciones(request):
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})
    resultados = MaestroInstitucion.objects.filter(nombre__icontains=query)[:15]
    data = [{'id': m.id, 'nombre': m.nombre} for m in resultados]
    return JsonResponse({'results': data})


@login_required
def api_agregar_comentario(request, ticket_id):
    """Agrega un comentario al ticket. Acceso para agentes (no clientes)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    perfil = request.user.perfil
    if perfil.rol == 'cliente':
        return JsonResponse({'error': 'Sin permisos'}, status=403)

    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    data = json.loads(request.body)
    texto = data.get('texto', '').strip()
    visibilidad = data.get('visibilidad', 'interno')

    if not texto:
        return JsonResponse({'error': 'El comentario no puede estar vacío'}, status=400)

    comentario = ComentarioTicket.objects.create(
        ticket=ticket,
        autor=request.user,
        texto=texto,
        visibilidad=visibilidad
    )

    LogActividad.objects.create(
        ticket=ticket, usuario=request.user,
        accion=f'Comentario {"interno" if visibilidad == "interno" else "público"} agregado',
        detalle=texto[:100]
    )

    return JsonResponse({
        'ok': True,
        'comentario': {
            'id': comentario.id,
            'texto': comentario.texto,
            'autor': request.user.get_full_name() or request.user.username,
            'visibilidad': comentario.visibilidad,
            'fecha': comentario.fecha.strftime('%d/%m/%Y %H:%M'),
        }
    })


@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor')
def api_reclasificar_ia(request, ticket_id):
    """Reclasifica un ticket usando la IA con aprendizaje. Devuelve sugerencia sin aplicar."""
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    resultado = reclasificar_ticket_con_ia(ticket)

    if resultado:
        return JsonResponse({'ok': True, 'clasificacion': resultado})
    return JsonResponse({'ok': False, 'error': 'IA no disponible en este momento'}, status=503)


@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor')
def api_aplicar_reclasificacion(request, ticket_id):
    """Aplica la reclasificación y guarda el feedback para aprendizaje."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    data = json.loads(request.body)

    # Guardar feedback de IA para aprendizaje
    FeedbackIA.objects.create(
        ticket=ticket,
        corrector=request.user,
        ia_linea_original=ticket.linea_servicio or '',
        ia_proceso_original=ticket.proceso or '',
        ia_tipificacion_original=ticket.tipificacion or '',
        ia_criticidad_original=ticket.criticidad or '',
        linea_corregida=data.get('linea', ''),
        proceso_corregido=data.get('proceso', ''),
        tipificacion_corregida=data.get('tipificacion', ''),
        criticidad_corregida=data.get('criticidad', ''),
        observacion=data.get('observacion', '')
    )

    # Aplicar nueva clasificación
    if data.get('linea'): ticket.linea_servicio = data['linea']
    if data.get('proceso'): ticket.proceso = data['proceso']
    if data.get('tipificacion'): ticket.tipificacion = data['tipificacion']
    if data.get('criticidad'): ticket.criticidad = data['criticidad']
    if data.get('analisis_ia'): ticket.analisis_ia = data['analisis_ia']
    ticket.clasificado_por_ia = True
    ticket.save()

    LogActividad.objects.create(
        ticket=ticket, usuario=request.user,
        accion='Reclasificación IA aplicada y feedback registrado',
        detalle=f'Nueva tipificación: {data.get("tipificacion")} | Criticidad: {data.get("criticidad")}'
    )

    return JsonResponse({'ok': True})


@login_required
def api_buscar_tickets(request):
    """Busca coincidencias agrupadas por categoría para el buscador inteligente.
    Resultados limitados a LIMITE_BUSQUEDA por grupo para prevenir timeouts.
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'grupos': [], 'total': 0})

    perfil = request.user.perfil
    # Base query según rol
    if perfil.rol in ['superadmin', 'admin_pqrs']:
        qs = Ticket.objects.all()
    elif perfil.rol == 'director_regional':
        qs = Ticket.objects.filter(regional=perfil.regional)
    elif perfil.rol == 'supervisor':
        filtro = Q(responsable__icontains=request.user.username)
        if request.user.get_full_name():
            filtro |= Q(responsable__icontains=request.user.get_full_name())
        if request.user.last_name:
            filtro |= Q(responsable__icontains=request.user.last_name)
        qs = Ticket.objects.filter(filtro)
    else:
        return JsonResponse({'grupos': [], 'total': 0})

    grupos = []

    # ── 1. CLIENTES (primera prioridad)
    # Solo clientes que tienen tickets visibles para este usuario (respeta rol)
    clientes_con_tickets_ids = qs.exclude(
        cliente_rel__isnull=True
    ).values_list('cliente_rel_id', flat=True).distinct()

    clientes_match = Cliente.objects.filter(
        id__in=clientes_con_tickets_ids,
        nombre__icontains=q
    ).distinct()[:6]

    items_clientes = []
    seen_clientes = set()
    for c in clientes_match:
        cant = qs.filter(cliente_rel=c).count()
        if cant > 0 and c.id not in seen_clientes:
            seen_clientes.add(c.id)
            items_clientes.append({
                'tipo': 'cliente',
                'texto': c.nombre,
                'subtexto': c.get_regional_display() if c.regional else 'Sin regional',
                'cantidad': cant,
                'accion': f'/dashboard/?cliente_id={c.id}',
                'id': c.id,
            })

    # También buscar entidades libres (tickets sin cliente_rel) que coincidan
    entidades = qs.filter(
        cliente_rel__isnull=True
    ).filter(
        Q(entidad_cliente__icontains=q) | Q(institucion__icontains=q)
    ).values_list('entidad_cliente', flat=True).distinct()[:4]

    seen_ent = set(c['texto'].lower() for c in items_clientes)
    for e in entidades:
        if e and e.strip() and e.lower() not in seen_ent:
            seen_ent.add(e.lower())
            cant = qs.filter(Q(entidad_cliente__iexact=e) | Q(institucion__iexact=e)).count()
            items_clientes.append({
                'tipo': 'entidad',
                'texto': e,
                'subtexto': 'Institución en tickets',
                'cantidad': cant,
                'accion': f'/dashboard/?q={e}',
            })

    if items_clientes:
        grupos.append({
            'titulo': 'Clientes / Instituciones',
            'icono': 'fa-hospital',
            'color': '#059669',
            'items': items_clientes,
        })

    # ── 2. RESPONSABLES
    responsables = qs.filter(responsable__icontains=q).exclude(
        responsable__isnull=True
    ).exclude(responsable='').values_list('responsable', flat=True).distinct()[:4]
    if responsables:
        items = []
        seen_r = set()
        for r in responsables:
            r_clean = r.strip()
            if r_clean.lower() not in seen_r:
                seen_r.add(r_clean.lower())
                cant = qs.filter(responsable__iexact=r_clean).count()
                items.append({
                    'tipo': 'responsable',
                    'texto': r_clean,
                    'subtexto': 'Personal asignado',
                    'cantidad': cant,
                    'accion': f'/dashboard/?q={r_clean}',
                })
        if items:
            grupos.append({
                'titulo': 'Responsables',
                'icono': 'fa-user-tie',
                'color': '#dc2626',
                'items': items,
            })

    # ── 3. REGIONALES
    for key, nombre in Ticket.REGIONAL_CHOICES:
        if q.lower() in nombre.lower() or q.lower() in key.lower():
            cant = qs.filter(regional=key).count()
            if cant > 0:
                if not any(g['titulo'] == 'Regionales' for g in grupos):
                    grupos.append({
                        'titulo': 'Regionales',
                        'icono': 'fa-map-location-dot',
                        'color': '#0ea5e9',
                        'items': [],
                    })
                for g in grupos:
                    if g['titulo'] == 'Regionales':
                        g['items'].append({
                            'tipo': 'regional',
                            'texto': nombre,
                            'subtexto': f'Código: {key}',
                            'cantidad': cant,
                            'accion': f'/dashboard/?q={nombre}',
                        })

    # ── 4. TICKETS ESPECÍFICOS (por ID)
    if 'PQRS' in q.upper() or q.upper().startswith('#'):
        tickets_match = qs.filter(ticket_id__icontains=q.replace('#', ''))[:5]
        if tickets_match:
            items = []
            for t in tickets_match:
                items.append({
                    'tipo': 'ticket',
                    'texto': t.ticket_id,
                    'subtexto': f'{t.remitente_nombre or t.entidad_cliente or "—"} · {t.asunto[:40] if t.asunto else "—"}',
                    'cantidad': None,
                    'accion': f'/ticket/{t.ticket_id}/',
                    'estado': t.get_estado_display(),
                    'sla': t.estado_sla(),
                })
            grupos.append({
                'titulo': 'Tickets',
                'icono': 'fa-hashtag',
                'color': '#3b82f6',
                'items': items,
            })

    # ── 5. COINCIDENCIAS POR ASUNTO (últimos)
    tickets_asunto = qs.filter(asunto__icontains=q)[:4]
    if tickets_asunto:
        items = []
        for t in tickets_asunto:
            items.append({
                'tipo': 'ticket',
                'texto': t.asunto[:55] if t.asunto else '—',
                'subtexto': f'{t.ticket_id} · {t.remitente_nombre or t.entidad_cliente or "—"}',
                'cantidad': None,
                'accion': f'/ticket/{t.ticket_id}/',
                'estado': t.get_estado_display(),
                'sla': t.estado_sla(),
            })
        grupos.append({
            'titulo': 'Coincidencias en Asunto',
            'icono': 'fa-align-left',
            'color': '#d97706',
            'items': items,
        })

    total_items = sum(len(g['items']) for g in grupos)
    return JsonResponse({
        'grupos': grupos,
        'total': total_items,
        'query': q,
    })


@login_required
def api_simular_rol(request):
    """
    Activa/desactiva la simulación de rol para el superadmin.

    POST { "rol": "director_regional", "regional": "llanos" }
    POST { "rol": "cliente", "cliente_id": 42 }
    POST { "rol": "agente" }
    POST { "rol": "" }  → desactiva
    """
    # Verificar que el usuario REAL es superadmin (no simulado)
    perfil_real_rol = request.rol_original or request.user.perfil.rol
    rol_real_session = request.session.get('_rol_real_superadmin', False)

    if perfil_real_rol != 'superadmin' and not rol_real_session:
        return JsonResponse({'ok': False, 'error': 'No autorizado.'}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        data = {}

    rol = data.get('rol', '').strip()
    roles_validos = ['admin_pqrs', 'director_regional', 'agente', 'cliente']

    if rol and rol in roles_validos:
        request.session['simular_rol'] = rol
        request.session['_rol_real_superadmin'] = True

        # ── Guardar regional si es director_regional ──
        if rol == 'director_regional':
            regional = data.get('regional', '').strip()
            request.session['simular_regional'] = regional

        # ── Guardar cliente_id si es cliente ──
        if rol == 'cliente':
            cliente_id = data.get('cliente_id')
            if cliente_id:
                request.session['simular_cliente_id'] = cliente_id
            else:
                request.session.pop('simular_cliente_id', None)

        # Determinar redirección
        if rol == 'cliente':
            redirect_url = '/cliente/dashboard/'
        else:
            redirect_url = '/dashboard/'

        rol_labels = {
            'admin_pqrs': 'Administrador PQRS',
            'director_regional': 'Director Regional',
            'agente': 'Agente / Consultor',
            'cliente': 'Cliente Institución',
        }

        return JsonResponse({
            'ok': True,
            'activo': True,
            'rol': rol,
            'rol_display': rol_labels.get(rol, rol),
            'redirect': redirect_url,
        })

    elif rol == '' or not rol:
        # Desactivar simulación — limpiar todo
        request.session.pop('simular_rol', None)
        request.session.pop('simular_regional', None)
        request.session.pop('simular_cliente_id', None)
        request.session.pop('_rol_real_superadmin', None)
        return JsonResponse({
            'ok': True,
            'activo': False,
            'redirect': '/dashboard/',
        })
    else:
        return JsonResponse({'ok': False, 'error': 'Rol no válido.'}, status=400)


@login_required
def api_simular_opciones(request):
    """
    Devuelve las opciones disponibles para sub-selects de simulación:
    - Regionales disponibles (para director_regional)
    - Clientes disponibles (para cliente)
    Solo accesible por superadmin.
    """
    if request.user.perfil.rol != 'superadmin' and not request.session.get('_rol_real_superadmin'):
        return JsonResponse({'ok': False}, status=403)

    regionales = Ticket.REGIONAL_CHOICES

    clientes = list(
        Cliente.objects.filter(activo=True).values('id', 'nombre', 'regional')
        .order_by('nombre')[:80]
    )

    return JsonResponse({
        'ok': True,
        'regionales': [{'key': k, 'label': v} for k, v in regionales],
        'clientes': clientes,
    })


