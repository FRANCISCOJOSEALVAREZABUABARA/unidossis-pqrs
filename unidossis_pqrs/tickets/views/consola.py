"""
Consola Central de Administración — UNIDOSSIS PQRS
Reemplaza la necesidad del Django Admin con una interfaz custom premium.
Módulos: Dashboard, Tablas Maestras, Permisos, Perfiles, Auditoría.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
import json

from ..models import (
    Ticket, Cliente, Ciudad, Cargo, MaestroInstitucion,
    PerfilUsuario, ConfiguracionSLA, LogActividad,
    ComentarioTicket, EncuestaSatisfaccion, FeedbackIA,
    IntentoLogin, SolicitudResetPassword, AlertaSLA,
    PermisoRol,
)
from ._helpers import rol_requerido


# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE TABLAS ADMINISTRABLES
# ═══════════════════════════════════════════════════════════════

TABLAS_CONSOLA = {
    'ciudades': {
        'model': Ciudad,
        'titulo': 'Ciudades / Municipios',
        'subtitulo': 'Catálogo de ciudades y municipios disponibles en el sistema.',
        'icono': 'fa-location-dot',
        'color': '#0ea5e9',
        'color_bg': '#e0f2fe',
        'campos': [
            {'field': 'nombre', 'label': 'Nombre', 'type': 'text', 'required': True, 'placeholder': 'Ej: Bogotá D.C.'},
        ],
        'display_fields': ['nombre'],
        'search_fields': ['nombre'],
        'ordering': ['nombre'],
    },
    'cargos': {
        'model': Cargo,
        'titulo': 'Cargos',
        'subtitulo': 'Catálogo de cargos disponibles para asignar a usuarios.',
        'icono': 'fa-id-badge',
        'color': '#8b5cf6',
        'color_bg': '#ede9fe',
        'campos': [
            {'field': 'nombre', 'label': 'Nombre del Cargo', 'type': 'text', 'required': True, 'placeholder': 'Ej: Director Técnico'},
        ],
        'display_fields': ['nombre'],
        'search_fields': ['nombre'],
        'ordering': ['nombre'],
    },
    'instituciones': {
        'model': MaestroInstitucion,
        'titulo': 'Maestro de Instituciones',
        'subtitulo': 'Catálogo de referencia de instituciones para autocompletado.',
        'icono': 'fa-hospital',
        'color': '#10b981',
        'color_bg': '#d1fae5',
        'campos': [
            {'field': 'nombre', 'label': 'Nombre de la Institución', 'type': 'text', 'required': True, 'placeholder': 'Ej: Fundación Cardioinfantil'},
        ],
        'display_fields': ['nombre'],
        'search_fields': ['nombre'],
        'ordering': ['nombre'],
    },
    'sla': {
        'model': ConfiguracionSLA,
        'titulo': 'Configuraciones SLA',
        'subtitulo': 'Umbrales de alerta y escalamiento para tickets PQRS.',
        'icono': 'fa-clock',
        'color': '#f59e0b',
        'color_bg': '#fef3c7',
        'campos': [
            {'field': 'nombre', 'label': 'Nombre', 'type': 'text', 'required': True, 'placeholder': 'Ej: SLA Principal'},
            {'field': 'dias_alerta_peligro', 'label': 'Días — Alerta Peligro', 'type': 'number', 'required': True, 'placeholder': '11'},
            {'field': 'dias_alerta_vencido', 'label': 'Días — Alerta Vencido', 'type': 'number', 'required': True, 'placeholder': '15'},
            {'field': 'emails_alerta_peligro', 'label': 'Emails Peligro (coma)', 'type': 'textarea', 'required': False, 'placeholder': 'a@unidossis.com, b@unidossis.com'},
            {'field': 'emails_alerta_vencido', 'label': 'Emails Vencido (coma)', 'type': 'textarea', 'required': False, 'placeholder': 'admin@unidossis.com'},
            {'field': 'celulares_alerta', 'label': 'Celulares (coma)', 'type': 'text', 'required': False, 'placeholder': '3001234567'},
            {'field': 'activo', 'label': 'Activo', 'type': 'checkbox', 'required': False, 'placeholder': ''},
        ],
        'display_fields': ['nombre', 'dias_alerta_peligro', 'dias_alerta_vencido', 'activo'],
        'search_fields': ['nombre'],
        'ordering': ['-activo', 'nombre'],
    },
}


# ═══════════════════════════════════════════════════════════════
# VISTA PRINCIPAL — DASHBOARD DE LA CONSOLA
# ═══════════════════════════════════════════════════════════════

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_central_view(request):
    """Dashboard principal de la Consola Central."""
    ahora = timezone.now()

    # KPIs
    total_usuarios = User.objects.filter(is_active=True).count()
    total_clientes = Cliente.objects.filter(activo=True).count()
    tickets_abiertos = Ticket.objects.filter(estado__in=['abierto', 'revision']).count()
    alertas_pendientes = AlertaSLA.objects.count()
    intentos_fallidos_24h = IntentoLogin.objects.filter(
        exitoso=False,
        fecha__gte=ahora - timezone.timedelta(hours=24)
    ).count()
    reset_pendientes = SolicitudResetPassword.objects.filter(estado='pendiente').count()

    # Actividad reciente (últimos 15 logs)
    actividad_reciente = LogActividad.objects.select_related('ticket', 'usuario').order_by('-fecha')[:15]

    # Resumen de tablas maestras
    tablas_resumen = []
    for key, config in TABLAS_CONSOLA.items():
        tablas_resumen.append({
            'key': key,
            'titulo': config['titulo'],
            'icono': config['icono'],
            'color': config['color'],
            'color_bg': config['color_bg'],
            'count': config['model'].objects.count(),
        })

    # Inventario de formularios/vistas registrados
    from tickets.context_processors import FORM_REGISTRY
    form_inventario = sorted(FORM_REGISTRY.values(), key=lambda f: f['code'])

    return render(request, 'tickets/consola_central.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'total_usuarios': total_usuarios,
        'total_clientes': total_clientes,
        'tickets_abiertos': tickets_abiertos,
        'alertas_pendientes': alertas_pendientes,
        'intentos_fallidos_24h': intentos_fallidos_24h,
        'reset_pendientes': reset_pendientes,
        'actividad_reciente': actividad_reciente,
        'tablas_resumen': tablas_resumen,
        'form_inventario': form_inventario,
    })


# ═══════════════════════════════════════════════════════════════
# INVENTARIO DE FORMULARIOS Y VISTAS
# ═══════════════════════════════════════════════════════════════

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_inventario_view(request):
    """Registro Central de Componentes — inventario de todos los formularios y vistas."""
    from tickets.models import RegistroComponente
    componentes = RegistroComponente.objects.filter(activo=True)

    return render(request, 'tickets/consola_inventario.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'form_inventario': componentes,
        'total_formularios': componentes.filter(tipo='formulario').count(),
        'total_vistas': componentes.filter(tipo='vista').count(),
    })


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_inventario_guardar(request):
    """API AJAX — Crear o editar un componente del inventario."""
    import json
    from tickets.models import RegistroComponente

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    pk = data.get('id')
    code = (data.get('code') or '').strip().upper()
    if not code:
        return JsonResponse({'ok': False, 'error': 'El código es obligatorio'}, status=400)

    tipo = 'vista' if code.startswith('V-') else 'formulario'

    if pk:
        # Editar existente
        try:
            comp = RegistroComponente.objects.get(pk=pk)
        except RegistroComponente.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'Componente no encontrado'}, status=404)
        comp.code = code
        comp.name = (data.get('name') or '').strip().upper()
        comp.full_name = (data.get('full_name') or '').strip()
        comp.version = (data.get('version') or 'v1.0.0').strip()
        comp.url_name = (data.get('url_name') or '').strip()
        comp.tablas = (data.get('tablas') or '').strip()
        comp.descripcion = (data.get('descripcion') or '').strip()
        comp.tipo = tipo
        comp.save()
    else:
        # Crear nuevo
        if RegistroComponente.objects.filter(code=code).exists():
            return JsonResponse({'ok': False, 'error': f'El código {code} ya existe'}, status=400)
        comp = RegistroComponente.objects.create(
            code=code,
            name=(data.get('name') or '').strip().upper(),
            full_name=(data.get('full_name') or '').strip(),
            version=(data.get('version') or 'v1.0.0').strip(),
            url_name=(data.get('url_name') or '').strip(),
            tablas=(data.get('tablas') or '').strip(),
            descripcion=(data.get('descripcion') or '').strip(),
            tipo=tipo,
        )

    return JsonResponse({'ok': True, 'id': comp.pk, 'code': comp.code})


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_inventario_eliminar(request, pk):
    """API AJAX — Eliminar (soft-delete) un componente del inventario."""
    from tickets.models import RegistroComponente

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    try:
        comp = RegistroComponente.objects.get(pk=pk)
    except RegistroComponente.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Componente no encontrado'}, status=404)

    comp.activo = False
    comp.save()
    return JsonResponse({'ok': True})


# ═══════════════════════════════════════════════════════════════
# TABLAS MAESTRAS — CRUD GENÉRICO
# ═══════════════════════════════════════════════════════════════

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_tabla_view(request, tabla):
    """Vista CRUD genérica para cualquier tabla maestra."""
    config = TABLAS_CONSOLA.get(tabla)
    if not config:
        return render(request, 'tickets/acceso_denegado.html', {
            'mensaje': f'La tabla "{tabla}" no existe en la consola.'
        }, status=404)

    Model = config['model']
    q = request.GET.get('q', '').strip()
    qs = Model.objects.all()

    # Búsqueda
    if q and config.get('search_fields'):
        query = Q()
        for f in config['search_fields']:
            query |= Q(**{f'{f}__icontains': q})
        qs = qs.filter(query)

    # Ordenamiento
    if config.get('ordering'):
        qs = qs.order_by(*config['ordering'])

    # Paginación
    paginator = Paginator(qs, 25)
    page = request.GET.get('page', 1)
    registros = paginator.get_page(page)

    return render(request, 'tickets/consola_tablas.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'tabla_key': tabla,
        'config': config,
        'registros': registros,
        'q': q,
        'total': paginator.count,
    })


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_consola_crear(request, tabla):
    """API AJAX — Crear registro en tabla maestra."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    config = TABLAS_CONSOLA.get(tabla)
    if not config:
        return JsonResponse({'ok': False, 'error': 'Tabla no existe'}, status=404)

    Model = config['model']

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except json.JSONDecodeError:
        data = request.POST

    kwargs = {}
    for campo in config['campos']:
        val = data.get(campo['field'], '')
        if campo['type'] == 'checkbox':
            val = val in (True, 'true', 'on', '1', 'True')
        elif campo['type'] == 'number' and val:
            try:
                val = int(val)
            except (ValueError, TypeError):
                return JsonResponse({'ok': False, 'error': f'El campo "{campo["label"]}" debe ser un número.'})
        if campo.get('required') and not val and campo['type'] != 'checkbox':
            return JsonResponse({'ok': False, 'error': f'El campo "{campo["label"]}" es obligatorio.'})
        kwargs[campo['field']] = val

    try:
        obj = Model.objects.create(**kwargs)
        LogActividad.objects.create(
            usuario=request.user,
            accion=f'[Consola] Creó registro en {config["titulo"]}: "{obj}"',
        )
        return JsonResponse({'ok': True, 'id': obj.pk, 'mensaje': f'Registro creado exitosamente.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_consola_editar(request, tabla, pk):
    """API AJAX — Editar registro en tabla maestra."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    config = TABLAS_CONSOLA.get(tabla)
    if not config:
        return JsonResponse({'ok': False, 'error': 'Tabla no existe'}, status=404)

    Model = config['model']
    obj = get_object_or_404(Model, pk=pk)

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except json.JSONDecodeError:
        data = request.POST

    for campo in config['campos']:
        val = data.get(campo['field'], '')
        if campo['type'] == 'checkbox':
            val = val in (True, 'true', 'on', '1', 'True')
        elif campo['type'] == 'number' and val:
            try:
                val = int(val)
            except (ValueError, TypeError):
                return JsonResponse({'ok': False, 'error': f'El campo "{campo["label"]}" debe ser un número.'})
        if campo.get('required') and not val and campo['type'] != 'checkbox':
            return JsonResponse({'ok': False, 'error': f'El campo "{campo["label"]}" es obligatorio.'})
        setattr(obj, campo['field'], val)

    try:
        obj.save()
        LogActividad.objects.create(
            usuario=request.user,
            accion=f'[Consola] Editó registro en {config["titulo"]}: "{obj}"',
        )
        return JsonResponse({'ok': True, 'mensaje': 'Registro actualizado.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def api_consola_eliminar(request, tabla, pk):
    """API AJAX — Eliminar registro de tabla maestra."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    config = TABLAS_CONSOLA.get(tabla)
    if not config:
        return JsonResponse({'ok': False, 'error': 'Tabla no existe'}, status=404)

    Model = config['model']
    obj = get_object_or_404(Model, pk=pk)
    nombre = str(obj)

    try:
        obj.delete()
        LogActividad.objects.create(
            usuario=request.user,
            accion=f'[Consola] Eliminó registro de {config["titulo"]}: "{nombre}"',
        )
        return JsonResponse({'ok': True, 'mensaje': f'"{nombre}" eliminado permanentemente.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)})


# ═══════════════════════════════════════════════════════════════
# MATRIZ DE PERMISOS POR ROL
# ═══════════════════════════════════════════════════════════════

# Permisos por defecto para inicialización
PERMISOS_DEFAULT = {
    'superadmin': {p[0]: True for p in PermisoRol.PERMISO_CHOICES},
    'admin_pqrs': {
        'ver_dashboard': True, 'crear_ticket': True, 'editar_ticket': True,
        'eliminar_ticket': False, 'responder_ticket': True, 'ver_reportes': True,
        'exportar_excel': True, 'gestionar_clientes': True, 'gestionar_usuarios': True,
        'configurar_sla': True, 'ver_monitoreo': False, 'ver_auditoria': True,
        'acceso_consola': True, 'ver_analisis_ia': True, 'reclasificar_ia': True,
    },
    'director_regional': {
        'ver_dashboard': True, 'crear_ticket': False, 'editar_ticket': True,
        'eliminar_ticket': False, 'responder_ticket': True, 'ver_reportes': True,
        'exportar_excel': True, 'gestionar_clientes': False, 'gestionar_usuarios': False,
        'configurar_sla': False, 'ver_monitoreo': False, 'ver_auditoria': False,
        'acceso_consola': False, 'ver_analisis_ia': True, 'reclasificar_ia': False,
    },
    'agente': {
        'ver_dashboard': True, 'crear_ticket': False, 'editar_ticket': True,
        'eliminar_ticket': False, 'responder_ticket': False, 'ver_reportes': False,
        'exportar_excel': False, 'gestionar_clientes': False, 'gestionar_usuarios': False,
        'configurar_sla': False, 'ver_monitoreo': False, 'ver_auditoria': False,
        'acceso_consola': False, 'ver_analisis_ia': True, 'reclasificar_ia': False,
    },
    'cliente': {
        'ver_dashboard': False, 'crear_ticket': False, 'editar_ticket': False,
        'eliminar_ticket': False, 'responder_ticket': False, 'ver_reportes': False,
        'exportar_excel': False, 'gestionar_clientes': False, 'gestionar_usuarios': False,
        'configurar_sla': False, 'ver_monitoreo': False, 'ver_auditoria': False,
        'acceso_consola': False, 'ver_analisis_ia': False, 'reclasificar_ia': False,
    },
}


def _inicializar_permisos():
    """Crea los permisos por defecto si no existen."""
    if PermisoRol.objects.exists():
        return
    for rol, permisos in PERMISOS_DEFAULT.items():
        for permiso_key, permitido in permisos.items():
            PermisoRol.objects.get_or_create(
                rol=rol, permiso=permiso_key,
                defaults={'permitido': permitido}
            )


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_permisos_view(request):
    """Vista de permisos con selector de rol."""
    _inicializar_permisos()

    roles = list(PerfilUsuario.ROL_CHOICES)
    permisos_list = PermisoRol.PERMISO_CHOICES
    rol_seleccionado = request.GET.get('rol', '')

    # Validar rol seleccionado
    roles_validos = [r[0] for r in roles]
    if rol_seleccionado and rol_seleccionado not in roles_validos:
        rol_seleccionado = ''

    # Label del rol seleccionado
    rol_seleccionado_label = dict(roles).get(rol_seleccionado, '')

    # Construir lista de permisos para el rol seleccionado
    permisos_rol = []
    permisos_activos = 0
    if rol_seleccionado:
        for perm_key, perm_label in permisos_list:
            if rol_seleccionado == 'superadmin':
                permitido = True
            else:
                obj = PermisoRol.objects.filter(rol=rol_seleccionado, permiso=perm_key).first()
                permitido = obj.permitido if obj else False
            permisos_rol.append({
                'key': perm_key,
                'label': perm_label,
                'permitido': permitido,
            })
            if permitido:
                permisos_activos += 1

    return render(request, 'tickets/consola_permisos.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'roles': roles,
        'permisos_list': permisos_list,
        'rol_seleccionado': rol_seleccionado,
        'rol_seleccionado_label': rol_seleccionado_label,
        'permisos_rol': permisos_rol,
        'permisos_activos': permisos_activos,
        'total_permisos': len(permisos_list),
    })


@login_required
@rol_requerido('superadmin')
def api_consola_permisos_guardar(request):
    """API AJAX — Guardar cambio de permiso individual (toggle)."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    rol = data.get('rol')
    permiso = data.get('permiso')
    permitido = data.get('permitido', False)

    if rol == 'superadmin':
        return JsonResponse({'ok': False, 'error': 'No se pueden modificar permisos del Super Administrador.'})

    # Validar
    roles_validos = [r[0] for r in PerfilUsuario.ROL_CHOICES]
    permisos_validos = [p[0] for p in PermisoRol.PERMISO_CHOICES]

    if rol not in roles_validos or permiso not in permisos_validos:
        return JsonResponse({'ok': False, 'error': 'Rol o permiso inválido.'})

    obj, created = PermisoRol.objects.update_or_create(
        rol=rol, permiso=permiso,
        defaults={'permitido': permitido}
    )

    permiso_display = dict(PermisoRol.PERMISO_CHOICES).get(permiso, permiso)
    rol_display = dict(PerfilUsuario.ROL_CHOICES).get(rol, rol)
    estado = 'activado' if permitido else 'desactivado'

    LogActividad.objects.create(
        usuario=request.user,
        accion=f'[Consola] {estado.capitalize()} permiso "{permiso_display}" para rol "{rol_display}"',
    )

    return JsonResponse({'ok': True, 'mensaje': f'Permiso {estado}.'})


@login_required
@rol_requerido('superadmin')
def api_consola_permisos_reset(request):
    """API AJAX — Resetear permisos a valores por defecto."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    PermisoRol.objects.all().delete()
    _inicializar_permisos()

    LogActividad.objects.create(
        usuario=request.user,
        accion='[Consola] Reseteó todos los permisos a valores predeterminados',
    )

    return JsonResponse({'ok': True, 'mensaje': 'Permisos reseteados a valores predeterminados.'})


# ═══════════════════════════════════════════════════════════════
# PERFILES DE USUARIO
# ═══════════════════════════════════════════════════════════════

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_perfiles_view(request):
    """Grid de tarjetas de todos los usuarios del sistema."""
    q = request.GET.get('q', '').strip()
    filtro_rol = request.GET.get('rol', '')

    perfiles = PerfilUsuario.objects.select_related('user', 'cliente').order_by('user__first_name')

    if q:
        perfiles = perfiles.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__username__icontains=q) |
            Q(user__email__icontains=q)
        )

    if filtro_rol:
        perfiles = perfiles.filter(rol=filtro_rol)

    return render(request, 'tickets/consola_perfiles.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'perfiles': perfiles,
        'q': q,
        'filtro_rol': filtro_rol,
        'ROL_CHOICES': PerfilUsuario.ROL_CHOICES,
        'REGIONAL_CHOICES': PerfilUsuario.REGIONAL_CHOICES,
    })


@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_perfil_detalle_view(request, user_id):
    """Vista de detalle/edición de un perfil de usuario."""
    user_obj = get_object_or_404(User, pk=user_id)
    perfil_obj = getattr(user_obj, 'perfil', None)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'editar_perfil':
            # Actualizar User
            user_obj.first_name = request.POST.get('first_name', '').strip()
            user_obj.last_name = request.POST.get('last_name', '').strip()
            user_obj.email = request.POST.get('email', '').strip()
            new_pass = request.POST.get('password', '').strip()
            if new_pass:
                user_obj.set_password(new_pass)
            user_obj.save()

            # Actualizar Perfil
            if perfil_obj:
                # Solo superadmin puede cambiar rol
                if request.user.perfil.rol == 'superadmin':
                    perfil_obj.rol = request.POST.get('rol', perfil_obj.rol)
                perfil_obj.regional = request.POST.get('regional', '') or None
                perfil_obj.telefono = request.POST.get('telefono', '').strip() or None
                perfil_obj.notas_admin = request.POST.get('notas_admin', '').strip() or None
                perfil_obj.save()

            LogActividad.objects.create(
                usuario=request.user,
                accion=f'[Consola] Editó perfil de "{user_obj.get_full_name() or user_obj.username}"',
            )
            return redirect('consola_perfiles')

        elif action == 'toggle_activo':
            if perfil_obj and perfil_obj.rol == 'superadmin':
                pass  # No permitir
            else:
                user_obj.is_active = not user_obj.is_active
                user_obj.save()
                LogActividad.objects.create(
                    usuario=request.user,
                    accion=f'[Consola] {"Activó" if user_obj.is_active else "Desactivó"} usuario "{user_obj.username}"',
                )
            return redirect('consola_perfil_detalle', user_id=user_id)

    # Historial de actividad de este usuario
    actividad = LogActividad.objects.filter(usuario=user_obj).order_by('-fecha')[:20]

    # Tickets donde es responsable
    tickets_asignados = Ticket.objects.filter(
        responsable__icontains=user_obj.get_full_name() or user_obj.username
    ).order_by('-fecha_ingreso')[:10]

    # Intentos de login
    intentos_login = IntentoLogin.objects.filter(
        username=user_obj.username
    ).order_by('-fecha')[:10]

    return render(request, 'tickets/consola_perfil_detalle.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'user_obj': user_obj,
        'perfil_obj': perfil_obj,
        'actividad': actividad,
        'tickets_asignados': tickets_asignados,
        'intentos_login': intentos_login,
        'ROL_CHOICES': PerfilUsuario.ROL_CHOICES,
        'REGIONAL_CHOICES': PerfilUsuario.REGIONAL_CHOICES,
    })


# ═══════════════════════════════════════════════════════════════
# AUDITORÍA
# ═══════════════════════════════════════════════════════════════

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def consola_auditoria_view(request):
    """Centro de auditoría con filtros y timeline."""
    q = request.GET.get('q', '').strip()
    usuario_filtro = request.GET.get('usuario', '')
    fecha_desde = request.GET.get('desde', '')
    fecha_hasta = request.GET.get('hasta', '')
    tab = request.GET.get('tab', 'actividad')

    # Tab: Actividad
    logs = LogActividad.objects.select_related('ticket', 'usuario').order_by('-fecha')

    if q:
        logs = logs.filter(Q(accion__icontains=q) | Q(detalle__icontains=q))
    if usuario_filtro:
        logs = logs.filter(usuario__id=usuario_filtro)
    if fecha_desde:
        logs = logs.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        logs = logs.filter(fecha__date__lte=fecha_hasta)

    paginator_logs = Paginator(logs, 30)
    page_logs = request.GET.get('page', 1)
    logs_page = paginator_logs.get_page(page_logs)

    # Tab: Intentos de Login
    intentos = IntentoLogin.objects.order_by('-fecha')
    paginator_intentos = Paginator(intentos, 30)
    page_intentos = request.GET.get('page_intentos', 1)
    intentos_page = paginator_intentos.get_page(page_intentos)

    # Tab: Solicitudes de reset
    resets = SolicitudResetPassword.objects.select_related('user', 'resuelta_por').order_by('-fecha_solicitud')

    # Usuarios para filtro
    usuarios_con_logs = User.objects.filter(
        logactividad__isnull=False
    ).distinct().order_by('first_name')

    return render(request, 'tickets/consola_auditoria.html', {
        'perfil': request.user.perfil,
        'nav_active': 'consola',
        'logs_page': logs_page,
        'intentos_page': intentos_page,
        'resets': resets,
        'q': q,
        'usuario_filtro': usuario_filtro,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'tab': tab,
        'usuarios_con_logs': usuarios_con_logs,
        'total_logs': paginator_logs.count,
    })
