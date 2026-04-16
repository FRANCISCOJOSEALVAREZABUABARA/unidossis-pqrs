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

from .models import (
    Ticket, ArchivoAdjunto, Cliente, Ciudad, Cargo, MaestroInstitucion,
    PerfilUsuario, ConfiguracionSLA, AlertaSLA, LogActividad,
    ComentarioTicket, EncuestaSatisfaccion, FeedbackIA, IntentoLogin
)
from .ia_engine import analizar_ticket_con_ia, conversar_con_analista_ia, reclasificar_ticket_con_ia


# ─────────────────────────────────────────────────────────────
# ERROR HANDLERS (404 / 500)
# ─────────────────────────────────────────────────────────────

def custom_404(request, exception):
    """Handler personalizado para errores 404."""
    return render(request, '404.html', status=404)


def custom_500(request):
    """Handler personalizado para errores 500."""
    return render(request, '500.html', status=500)




# ─────────────────────────────────────────────────────────────
# DECORADORES DE ROLES
# ─────────────────────────────────────────────────────────────

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

            if request.user.perfil.rol not in roles and 'superadmin' not in [request.user.perfil.rol]:
                return render(request, 'tickets/acceso_denegado.html', {
                    'mensaje': f'El rol {request.user.perfil.get_rol_display()} no tiene permisos para esta sección.'
                }, status=403)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


# ─────────────────────────────────────────────────────────────
# HELPERS DE EMAIL
# ─────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────
# CAMBIAR CONTRASEÑA (Autoservicio)
# ─────────────────────────────────────────────────────────────

@login_required
def cambiar_password_view(request):
    """Permite a cualquier usuario autenticado cambiar su propia contraseña."""
    if request.method != 'POST':
        return JsonResponse({'tipo': 'error', 'texto': 'Método no permitido.'}, status=405)

    current_password = request.POST.get('current_password', '')
    new_password = request.POST.get('new_password', '')
    confirm_password = request.POST.get('confirm_password', '')

    if not request.user.check_password(current_password):
        return JsonResponse({'tipo': 'error', 'texto': 'La contraseña actual es incorrecta.'})

    if len(new_password) < 8:
        return JsonResponse({'tipo': 'error', 'texto': 'La nueva contraseña debe tener al menos 8 caracteres.'})

    if new_password != confirm_password:
        return JsonResponse({'tipo': 'error', 'texto': 'Las contraseñas nuevas no coinciden.'})

    if current_password == new_password:
        return JsonResponse({'tipo': 'error', 'texto': 'La nueva contraseña debe ser diferente a la actual.'})

    request.user.set_password(new_password)
    request.user.save()
    update_session_auth_hash(request, request.user)  # Mantener la sesión activa

    # Desactivar el flag de cambio forzado de contraseña
    if hasattr(request.user, 'perfil'):
        request.user.perfil.debe_cambiar_password = False
        request.user.perfil.save(update_fields=['debe_cambiar_password'])

    return JsonResponse({'tipo': 'exito', 'texto': 'Su contraseña ha sido actualizada exitosamente.'})


# ─────────────────────────────────────────────────────────────
# DASHBOARD PRINCIPAL
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor')
def dashboard_view(request):
    perfil = request.user.perfil

    # Base query según rol
    if perfil.rol in ['superadmin', 'admin_pqrs']:
        tickets_query = Ticket.objects.all()
    elif perfil.rol == 'director_regional':
        tickets_query = Ticket.objects.filter(regional=perfil.regional)
    elif perfil.rol == 'supervisor':
        # Buscar por username, nombre completo o apellido del supervisor
        nombre_completo = request.user.get_full_name()
        filtro_supervisor = Q(responsable__icontains=request.user.username)
        if nombre_completo:
            filtro_supervisor |= Q(responsable__icontains=nombre_completo)
        if request.user.last_name:
            filtro_supervisor |= Q(responsable__icontains=request.user.last_name)
        if request.user.first_name:
            filtro_supervisor |= Q(responsable__icontains=request.user.first_name)
        tickets_query = Ticket.objects.filter(filtro_supervisor)

    # Filtro por cliente (Para Inteligencia Analítica)
    cliente_id = request.GET.get('cliente_id')
    if cliente_id:
        tickets_query = tickets_query.filter(cliente_rel_id=cliente_id)

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
    }
    return render(request, 'tickets/dashboard.html', context)


# ─────────────────────────────────────────────────────────────
# DETALLE DE TICKET
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional', 'supervisor', 'cliente')
def ticket_detail_view(request, ticket_id):
    ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
    perfil = request.user.perfil

    # Validaciones de seguridad por rol
    if perfil.rol == 'cliente':
        if ticket.cliente_rel != perfil.cliente:
            return redirect('acceso_denegado')
    elif perfil.rol == 'director_regional':
        if ticket.regional != perfil.regional:
            return redirect('acceso_denegado')
    elif perfil.rol == 'supervisor':
        responsable_str = (ticket.responsable or "").lower()
        puede_ver = (
            request.user.username.lower() in responsable_str or
            (request.user.get_full_name() and request.user.get_full_name().lower() in responsable_str) or
            (request.user.last_name and request.user.last_name.lower() in responsable_str)
        )
        if not puede_ver and not request.user.is_superuser:
            return redirect('acceso_denegado')

    adjuntos_cliente = ticket.archivos_adjuntos.filter(es_respuesta_agente=False)
    adjuntos_unidossis = ticket.archivos_adjuntos.filter(es_respuesta_agente=True)
    comentarios = ticket.comentarios.all()
    logs = ticket.logs.all()[:20]

    if request.method == 'POST' and perfil.rol != 'cliente':
        estado_anterior = ticket.estado
        nuevo_estado = request.POST.get('nuevo_estado')
        respuesta_texto = request.POST.get('respuesta_oficial')

        if nuevo_estado in dict(Ticket.STATUS_CHOICES):
            ticket.estado = nuevo_estado

        proceso = request.POST.get('proceso')
        linea = request.POST.get('linea_servicio')
        tipificacion = request.POST.get('tipificacion')
        criticidad = request.POST.get('criticidad')

        if proceso: ticket.proceso = proceso
        if linea: ticket.linea_servicio = linea
        if tipificacion: ticket.tipificacion = tipificacion
        if criticidad: ticket.criticidad = criticidad

        responsable_manual = request.POST.get('responsable')
        if responsable_manual: ticket.responsable = responsable_manual

        if respuesta_texto is not None:
            ticket.respuesta_oficial = respuesta_texto

        ticket.save()

        # Log de actividad automático
        if nuevo_estado and nuevo_estado != estado_anterior:
            LogActividad.objects.create(
                ticket=ticket, usuario=request.user,
                accion=f'Estado cambiado: {estado_anterior} → {nuevo_estado}',
                detalle=f'Cambiado por: {request.user.get_full_name() or request.user.username}'
            )

        # Archivos adjuntos del agente
        if request.FILES.getlist('archivos_agente'):
            for archivo_subido in request.FILES.getlist('archivos_agente'):
                ArchivoAdjunto.objects.create(
                    ticket=ticket,
                    archivo=archivo_subido,
                    es_respuesta_agente=True,
                    subido_por_sistema=False
                )

        # Cerrar y enviar respuesta formal + CSAT
        if 'cerrar_y_enviar' in request.POST:
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
        'comentarios': comentarios,
        'logs': logs,
        'STATUS_CHOICES': Ticket.STATUS_CHOICES,
        'AREA_CHOICES': Ticket.AREA_CHOICES,
        'LINEA_CHOICES': Ticket.LINEA_CHOICES,
        'TIPIFICACION_CHOICES': Ticket.TIPIFICACION_CHOICES,
        'CRITICIDAD_CHOICES': Ticket.CRITICIDAD_CHOICES,
        'perfil': perfil,
        'nav_active': 'dashboard',
        'cliente': perfil.cliente if perfil.rol == 'cliente' else None,
    })


# ─────────────────────────────────────────────────────────────
# PORTAL PÚBLICO DE CLIENTES
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('cliente')
def public_pqrs_view(request):
    perfil_cliente = getattr(request.user, 'cliente_perfil', None)

    if perfil_cliente and not perfil_cliente.activo:
        return render(request, 'tickets/acceso_denegado.html', {
            'mensaje': 'Su cuenta institucional se encuentra inactiva. Comuníquese con el equipo de Unidossis para más información.'
        }, status=403)

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
            return render(request, 'tickets/portal_form.html', {
                'TIPO_CHOICES': Ticket.TIPO_SOLICITUD_CHOICES,
                'perfil_cliente': perfil_cliente,
                'error': 'Por favor, complete todos los campos obligatorios (Institución, Nombre, Correo, Asunto y Descripción).'
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

        # El portal de clientes NO envía acuse de recibo (solo correos externos)
        return render(request, 'tickets/portal_success.html', {'ticket': nuevo_ticket})

    return render(request, 'tickets/portal_form.html', {
        'TIPO_CHOICES': Ticket.TIPO_SOLICITUD_CHOICES,
        'perfil_cliente': perfil_cliente
    })


# ─────────────────────────────────────────────────────────────
# LOGIN / LOGOUT
# ─────────────────────────────────────────────────────────────

def _get_client_ip(request):
    """Obtiene la IP real del cliente (soporta proxies)."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def login_view(request):
    MAX_INTENTOS = 5
    MINUTOS_BLOQUEO = 15

    if request.method == 'POST':
        ip = _get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        username_input = request.POST.get('username', '')

        # ── Rate limiting: verificar intentos recientes ──
        desde = timezone.now() - timezone.timedelta(minutes=MINUTOS_BLOQUEO)
        intentos_fallidos = IntentoLogin.objects.filter(
            ip=ip, exitoso=False, fecha__gte=desde
        ).count()

        if intentos_fallidos >= MAX_INTENTOS:
            # Registrar intento bloqueado
            IntentoLogin.objects.create(ip=ip, username=username_input, exitoso=False, user_agent=user_agent)
            return render(request, 'tickets/login.html', {
                'form': AuthenticationForm(),
                'error_bloqueo': f'Demasiados intentos fallidos. Intente de nuevo en {MINUTOS_BLOQUEO} minutos.'
            })

        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Registrar login exitoso
            IntentoLogin.objects.create(ip=ip, username=user.username, exitoso=True, user_agent=user_agent)

            # Log de auditoría
            LogActividad.objects.create(
                ticket=None, usuario=user,
                accion='Inicio de sesión',
                detalle=f'IP: {ip} | Navegador: {user_agent[:100]}'
            )

            try:
                perfil = user.perfil

                # ── Cambio forzado de contraseña ──
                if perfil.debe_cambiar_password:
                    return render(request, 'tickets/cambiar_password_obligatorio.html', {
                        'perfil': perfil,
                    })

                if perfil.rol == 'cliente':
                    return redirect('portal_cliente_dashboard')
                elif perfil.rol in ['superadmin', 'admin_pqrs']:
                    return redirect('gestionar_clientes')
                else:
                    return redirect('dashboard')
            except PerfilUsuario.DoesNotExist:
                if user.is_superuser:
                    return redirect('gestionar_clientes')
                return redirect('dashboard')
        else:
            # Registrar intento fallido
            IntentoLogin.objects.create(ip=ip, username=username_input, exitoso=False, user_agent=user_agent)
    else:
        form = AuthenticationForm()
    return render(request, 'tickets/login.html', {'form': form})


def logout_view(request):
    # Log de auditoría antes del logout
    if request.user.is_authenticated:
        ip = _get_client_ip(request)
        LogActividad.objects.create(
            ticket=None, usuario=request.user,
            accion='Cierre de sesión',
            detalle=f'IP: {ip}'
        )
    logout(request)
    return redirect('login')


# ─────────────────────────────────────────────────────────────
# GESTIÓN DE CLIENTES
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def gestionar_clientes_view(request):
    """Panel para que el admin asigne usuario y contraseña a los clientes."""
    mensaje = None

    if request.method == 'POST':
        action = request.POST.get('action')
        is_ajax = request.POST.get('is_ajax') == '1'

        if action == 'crear':
            cliente_id = request.POST.get('cliente_id')
            username = request.POST.get('username')
            password = request.POST.get('password')
            email = request.POST.get('email', '')

            if cliente_id and username and password:
                try:
                    cliente = Cliente.objects.get(id=cliente_id)
                    if User.objects.filter(username=username).exists():
                        mensaje = {'tipo': 'error', 'texto': f'El usuario "{username}" ya existe.'}
                    else:
                        nuevo_user = User.objects.create_user(username=username, password=password, email=email)
                        nuevo_user.first_name = cliente.nombre[:30]
                        nuevo_user.save()
                        cliente.user = nuevo_user
                        PerfilUsuario.objects.get_or_create(
                            user=nuevo_user,
                            defaults={'rol': 'cliente', 'cliente': cliente}
                        )
                        nueva_regional = request.POST.get('regional')
                        nuevo_email_p = request.POST.get('email_principal')
                        nuevo_email_a = request.POST.get('emails_adicionales')
                        if nueva_regional: cliente.regional = nueva_regional
                        if nuevo_email_p: cliente.email_principal = nuevo_email_p
                        if nuevo_email_a: cliente.emails_adicionales = nuevo_email_a
                        cliente.save()
                        mensaje = {'tipo': 'exito', 'texto': f'Acceso creado para {cliente.nombre}: usuario "{username}".'}
                except Cliente.DoesNotExist:
                    mensaje = {'tipo': 'error', 'texto': 'Cliente no encontrado.'}

        elif action == 'cambiar_password':
            user_id = request.POST.get('user_id')
            new_password = request.POST.get('new_password')
            if user_id and new_password:
                try:
                    user_obj = User.objects.get(id=user_id)
                    user_obj.set_password(new_password)
                    user_obj.save()
                    mensaje = {'tipo': 'exito', 'texto': f'Contraseña actualizada para {user_obj.username}.'}
                except User.DoesNotExist:
                    mensaje = {'tipo': 'error', 'texto': 'Usuario no encontrado.'}

        elif action == 'crear_institucion':
            nombre_institucion = request.POST.get('nombre_institucion', '').strip()
            ciudad_id = request.POST.get('ciudad_id')
            regional = request.POST.get('regional')
            email_p = request.POST.get('email_principal', '').strip()
            emails_a = request.POST.get('emails_adicionales', '').strip()
            if nombre_institucion and email_p:
                if Cliente.objects.filter(nombre__iexact=nombre_institucion).exists():
                    mensaje = {'tipo': 'error', 'texto': f'La institución "{nombre_institucion}" ya existe.'}
                else:
                    nueva_inst = Cliente.objects.create(
                        nombre=nombre_institucion, email_principal=email_p,
                        emails_adicionales=emails_a, regional=regional
                    )
                    MaestroInstitucion.objects.get_or_create(nombre=nombre_institucion)
                    if ciudad_id:
                        try:
                            nueva_inst.ciudad = Ciudad.objects.get(id=ciudad_id)
                            nueva_inst.save()
                        except Ciudad.DoesNotExist:
                            pass
                    mensaje = {'tipo': 'exito', 'texto': f'"{nueva_inst.nombre}" ha sido creada exitosamente.'}
            else:
                mensaje = {'tipo': 'error', 'texto': 'El nombre y el correo principal son obligatorios.'}

        elif action == 'inactivar':
            cliente_id = request.POST.get('cliente_id')
            try:
                cliente = Cliente.objects.get(id=cliente_id)
                cliente.activo = not cliente.activo
                cliente.save()
                estado_txt = 'activado' if cliente.activo else 'marcado como inactivo'
                mensaje = {'tipo': 'exito', 'texto': f'"{cliente.nombre}" ha sido {estado_txt} exitosamente.'}
            except Cliente.DoesNotExist:
                mensaje = {'tipo': 'error', 'texto': 'Cliente no encontrado.'}

        elif action == 'editar_cliente':
            cliente_id = request.POST.get('cliente_id')
            nombre = request.POST.get('nombre', '').strip()
            regional = request.POST.get('regional')
            email_p = request.POST.get('email_principal', '').strip()
            emails_a = request.POST.get('emails_adicionales', '').strip()
            ciudad_id = request.POST.get('ciudad_id')
            activo = request.POST.get('activo') == 'on'
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            try:
                cliente = Cliente.objects.get(id=cliente_id)
                cliente.nombre = nombre
                cliente.regional = regional
                cliente.email_principal = email_p
                cliente.emails_adicionales = emails_a
                cliente.activo = activo
                if ciudad_id:
                    try:
                        cliente.ciudad = Ciudad.objects.get(id=ciudad_id)
                    except Ciudad.DoesNotExist:
                        pass
                if username and not cliente.user:
                    if User.objects.filter(username=username).exists():
                        mensaje = {'tipo': 'error', 'texto': f'El usuario "{username}" ya está en uso.'}
                    else:
                        nuevo_user = User.objects.create_user(username=username, password=password or '12345', email=email_p)
                        nuevo_user.first_name = cliente.nombre[:30]
                        nuevo_user.save()
                        PerfilUsuario.objects.get_or_create(
                            user=nuevo_user, defaults={'rol': 'cliente', 'cliente': cliente}
                        )
                        cliente.user = nuevo_user
                elif cliente.user and password:
                    cliente.user.set_password(password)
                    cliente.user.save()
                cliente.save()
                mensaje = {'tipo': 'exito', 'texto': f'Configuración de "{cliente.nombre}" actualizada con éxito.'}
            except Cliente.DoesNotExist:
                mensaje = {'tipo': 'error', 'texto': 'Cliente no encontrado.'}

        elif action == 'eliminar':
            cliente_id = request.POST.get('cliente_id')
            try:
                cliente = Cliente.objects.get(id=cliente_id)
                nombre_eliminado = cliente.nombre
                if cliente.user:
                    cliente.user.delete()
                else:
                    cliente.delete()
                mensaje = {'tipo': 'exito', 'texto': f'"{nombre_eliminado}" ha sido eliminado permanentemente del sistema.'}
            except Cliente.DoesNotExist:
                mensaje = {'tipo': 'error', 'texto': 'Cliente no encontrado.'}

        # ─── Acciones de Usuarios Internos ────────────────────
        elif action == 'crear_usuario':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            rol = request.POST.get('rol', '')
            regional = request.POST.get('regional', '') or None

            if username and password and rol:
                if User.objects.filter(username=username).exists():
                    mensaje = {'tipo': 'error', 'texto': f'El usuario "{username}" ya existe en el sistema.'}
                else:
                    nuevo_user = User.objects.create_user(
                        username=username, password=password,
                        email=email, first_name=first_name, last_name=last_name
                    )
                    nuevo_user.is_staff = True
                    nuevo_user.save()
                    telefono = request.POST.get('telefono', '').strip()
                    PerfilUsuario.objects.create(user=nuevo_user, rol=rol, regional=regional, telefono=telefono or None)
                    rol_display = dict(PerfilUsuario.ROL_CHOICES).get(rol, rol)
                    mensaje = {'tipo': 'exito', 'texto': f'Usuario "{username}" creado exitosamente como {rol_display}.'}
            else:
                mensaje = {'tipo': 'error', 'texto': 'Nombre de usuario, contraseña y rol son obligatorios.'}

        elif action == 'editar_usuario':
            user_id = request.POST.get('user_id')
            try:
                user_obj = User.objects.get(id=user_id)
                if hasattr(user_obj, 'perfil') and user_obj.perfil.rol == 'superadmin':
                    mensaje = {'tipo': 'error', 'texto': 'No se puede editar un Super Administrador desde esta consola.'}
                else:
                    new_username = request.POST.get('username', '').strip()
                    # Validar username único (si cambió)
                    if new_username and new_username != user_obj.username:
                        if User.objects.filter(username=new_username).exclude(id=user_obj.id).exists():
                            mensaje = {'tipo': 'error', 'texto': f'El usuario "{new_username}" ya existe en el sistema.'}
                        else:
                            user_obj.username = new_username
                    if not mensaje:  # Solo continuar si no hubo error
                        user_obj.first_name = request.POST.get('first_name', '').strip()
                        user_obj.last_name = request.POST.get('last_name', '').strip()
                        user_obj.email = request.POST.get('email', '').strip()
                        new_pass = request.POST.get('password', '').strip()
                        if new_pass:
                            user_obj.set_password(new_pass)
                        user_obj.save()
                        perfil_obj = user_obj.perfil
                        perfil_obj.rol = request.POST.get('rol', perfil_obj.rol)
                        perfil_obj.regional = request.POST.get('regional', '') or None
                        perfil_obj.telefono = request.POST.get('telefono', '').strip() or None
                        perfil_obj.save()
                        mensaje = {'tipo': 'exito', 'texto': f'Usuario "{user_obj.username}" actualizado correctamente.'}
            except User.DoesNotExist:
                mensaje = {'tipo': 'error', 'texto': 'Usuario no encontrado.'}

        elif action == 'toggle_usuario':
            user_id = request.POST.get('user_id')
            try:
                user_obj = User.objects.get(id=user_id)
                if hasattr(user_obj, 'perfil') and user_obj.perfil.rol == 'superadmin':
                    mensaje = {'tipo': 'error', 'texto': 'No se puede desactivar un Super Administrador.'}
                else:
                    user_obj.is_active = not user_obj.is_active
                    user_obj.save()
                    estado_txt = 'activado' if user_obj.is_active else 'desactivado'
                    mensaje = {'tipo': 'exito', 'texto': f'Usuario "{user_obj.username}" ha sido {estado_txt}.'}
            except User.DoesNotExist:
                mensaje = {'tipo': 'error', 'texto': 'Usuario no encontrado.'}

        elif action == 'eliminar_usuario':
            user_id = request.POST.get('user_id')
            try:
                user_obj = User.objects.get(id=user_id)
                if hasattr(user_obj, 'perfil') and user_obj.perfil.rol == 'superadmin':
                    mensaje = {'tipo': 'error', 'texto': 'No se puede eliminar un Super Administrador.'}
                else:
                    nombre_usr = user_obj.get_full_name() or user_obj.username
                    user_obj.delete()
                    mensaje = {'tipo': 'exito', 'texto': f'Usuario "{nombre_usr}" eliminado permanentemente del sistema.'}
            except User.DoesNotExist:
                mensaje = {'tipo': 'error', 'texto': 'Usuario no encontrado.'}

        if is_ajax and mensaje:
            return JsonResponse(mensaje)

    clientes_sin_acceso = Cliente.objects.filter(user__isnull=True)[:50]
    todos_los_clientes = Cliente.objects.all().select_related('user', 'ciudad')

    # Usuarios internos (excluye clientes y superadmins)
    usuarios_internos = PerfilUsuario.objects.filter(
        rol__in=['admin_pqrs', 'director_regional', 'supervisor']
    ).select_related('user').order_by('user__first_name')

    ROL_CHOICES_INTERNOS = [
        ('admin_pqrs', 'Administrador PQRS'),
        ('director_regional', 'Director Regional'),
        ('supervisor', 'Supervisor'),
    ]

    tab_activa = request.POST.get('_tab', request.GET.get('tab', 'clientes'))

    return render(request, 'tickets/gestionar_clientes.html', {
        'clientes_sin_acceso': clientes_sin_acceso,
        'todos_los_clientes': todos_los_clientes,
        'usuarios_internos': usuarios_internos,
        'mensaje': mensaje,
        'REGIONAL_CHOICES': Cliente.REGIONAL_CHOICES,
        'ROL_CHOICES_INTERNOS': ROL_CHOICES_INTERNOS,
        'perfil': request.user.perfil,
        'nav_active': 'clientes',
        'tab_activa': tab_activa,
    })


# ─────────────────────────────────────────────────────────────
# PORTAL CLIENTE DASHBOARD
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('cliente')
def portal_cliente_dashboard(request):
    """Dashboard para que el cliente vea sus propios tickets."""
    perfil = request.user.perfil
    cliente = perfil.cliente

    if not cliente:
        return render(request, 'tickets/acceso_denegado.html', {
            'mensaje': 'Su usuario no está vinculado a ninguna institución clínica.'
        })

    tickets = Ticket.objects.filter(cliente_rel=cliente).order_by('-fecha_ingreso')
    tickets_en_proceso = tickets.exclude(estado__in=['resuelto', 'cancelado']).count()
    tickets_resueltos = tickets.filter(estado='resuelto').count()
    total_tickets = tickets.count()

    return render(request, 'tickets/cliente/dashboard.html', {
        'cliente': cliente,
        'tickets': tickets,
        'tickets_en_proceso': tickets_en_proceso,
        'tickets_resueltos': tickets_resueltos,
        'total_tickets': total_tickets,
        'nav_active': 'mis_pqrs',
    })


# ─────────────────────────────────────────────────────────────
# ACCESO DENEGADO
# ─────────────────────────────────────────────────────────────

def acceso_denegado_view(request):
    """Vista genérica para errores de permisos."""
    mensaje = request.GET.get('mensaje', 'No tiene permisos para acceder a esta sección.')
    return render(request, 'tickets/acceso_denegado.html', {'mensaje': mensaje})


# ─────────────────────────────────────────────────────────────
# APIs AJAX
# ─────────────────────────────────────────────────────────────

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
    resultados = Cliente.objects.filter(nombre__icontains=query)[:15]
    data = [{'nombre': c.nombre} for c in resultados]
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


# ─────────────────────────────────────────────────────────────
# COMENTARIOS POR TICKET (AJAX)
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# RECLASIFICACIÓN IA (AJAX)
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# CONFIGURACIÓN SLA
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin', 'admin_pqrs')
def configurar_sla_view(request):
    """Panel para parametrizar el SLA. Los destinatarios se obtienen de los usuarios internos."""
    config = ConfiguracionSLA.objects.filter(activo=True).first()
    mensaje = None

    if request.method == 'POST':
        dias_peligro = int(request.POST.get('dias_alerta_peligro', 11))
        dias_vencido = int(request.POST.get('dias_alerta_vencido', 15))

        if config:
            config.dias_alerta_peligro = dias_peligro
            config.dias_alerta_vencido = dias_vencido
            config.save()
        else:
            config = ConfiguracionSLA.objects.create(
                dias_alerta_peligro=dias_peligro,
                dias_alerta_vencido=dias_vencido,
                activo=True
            )
        mensaje = {'tipo': 'exito', 'texto': 'Configuración SLA guardada exitosamente.'}

    # Destinatarios automáticos desde Usuarios Internos
    directores_regionales = PerfilUsuario.objects.filter(
        rol='director_regional'
    ).select_related('user').order_by('regional')

    admins_pqrs = PerfilUsuario.objects.filter(
        rol__in=['admin_pqrs', 'superadmin']
    ).select_related('user').order_by('user__first_name')

    return render(request, 'tickets/configurar_sla.html', {
        'config': config,
        'mensaje': mensaje,
        'perfil': request.user.perfil,
        'nav_active': 'sla',
        'directores_regionales': directores_regionales,
        'admins_pqrs': admins_pqrs,
    })


# ─────────────────────────────────────────────────────────────
# REPORTES Y ANALYTICS (ESTILO POWER BI)
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional')
def reportes_view(request):
    """Dashboard de analytics avanzado con KPIs interactivos."""
    perfil = request.user.perfil

    # Base query según rol
    if perfil.rol in ['superadmin', 'admin_pqrs']:
        qs = Ticket.objects.all()
    else:
        qs = Ticket.objects.filter(regional=perfil.regional)

    # ─ Filtros de fecha
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    if fecha_inicio:
        qs = qs.filter(fecha_ingreso__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha_ingreso__date__lte=fecha_fin)

    total = qs.count()
    resueltos = qs.filter(estado='resuelto').count()
    abiertos = qs.filter(estado='abierto').count()
    en_revision = qs.filter(estado='revision').count()
    cancelados = qs.filter(estado='cancelado').count()
    cumplimiento_sla = round((resueltos / total * 100), 1) if total > 0 else 0

    # Calcular vencidos sobre abiertos reales
    tickets_abiertos_list = list(qs.exclude(estado__in=['resuelto', 'cancelado']))
    vencidos_count = sum(1 for t in tickets_abiertos_list if t.estado_sla() == 'vencido')
    peligro_count = sum(1 for t in tickets_abiertos_list if t.estado_sla() == 'peligro')

    # ─ Por tipificación (top 8)
    por_tipificacion = list(
        qs.exclude(tipificacion__isnull=True).values('tipificacion')
        .annotate(total=Count('id')).order_by('-total')[:8]
    )

    # ─ Por regional
    por_regional = list(
        qs.exclude(regional__isnull=True).values('regional')
        .annotate(total=Count('id')).order_by('-total')
    )
    # Mapear códigos a labels
    regional_map = dict(Ticket.REGIONAL_CHOICES)
    for r in por_regional:
        r['label'] = regional_map.get(r['regional'], r['regional'])

    # ─ Por tipo de solicitud
    por_tipo = list(
        qs.values('tipo_solicitud').annotate(total=Count('id')).order_by('-total')
    )
    tipo_map = dict(Ticket.TIPO_SOLICITUD_CHOICES)
    for t in por_tipo:
        t['label'] = tipo_map.get(t['tipo_solicitud'], t['tipo_solicitud'])

    # ─ Por criticidad
    por_criticidad = list(
        qs.exclude(criticidad__isnull=True).values('criticidad')
        .annotate(total=Count('id')).order_by('-total')
    )
    criticidad_map = dict(Ticket.CRITICIDAD_CHOICES)
    for c in por_criticidad:
        c['label'] = criticidad_map.get(c['criticidad'], c['criticidad'])

    # ─ Tendencia mensual (últimos 6 meses)
    from django.db.models.functions import TruncMonth
    tendencia = list(
        qs.annotate(mes=TruncMonth('fecha_ingreso'))
        .values('mes').annotate(total=Count('id')).order_by('mes')
    )

    # ─ CSAT promedio
    encuestas = EncuestaSatisfaccion.objects.filter(
        ticket__in=qs, estado='satisfecho', puntuacion__isnull=False
    )
    csat_promedio = encuestas.aggregate(avg=Avg('puntuacion'))['avg']
    csat_promedio = round(csat_promedio, 1) if csat_promedio else None
    total_encuestas = encuestas.count()

    context = {
        'perfil': perfil,
        'total': total,
        'resueltos': resueltos,
        'abiertos': abiertos,
        'en_revision': en_revision,
        'cancelados': cancelados,
        'cumplimiento_sla': cumplimiento_sla,
        'vencidos_count': vencidos_count,
        'peligro_count': peligro_count,
        'csat_promedio': csat_promedio,
        'total_encuestas': total_encuestas,
        # Datos JSON para Chart.js
        'por_tipificacion_json': json.dumps(por_tipificacion, default=str),
        'por_regional_json': json.dumps(por_regional, default=str),
        'por_tipo_json': json.dumps(por_tipo, default=str),
        'por_criticidad_json': json.dumps(por_criticidad, default=str),
        'tendencia_json': json.dumps(tendencia, default=str),
        'fecha_inicio': fecha_inicio or '',
        'fecha_fin': fecha_fin or '',
        'nav_active': 'reportes',
    }
    return render(request, 'tickets/reportes.html', context)


# ─────────────────────────────────────────────────────────────
# EXPORTACIÓN A EXCEL
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin', 'admin_pqrs', 'director_regional')
def exportar_excel_view(request):
    """Exporta los tickets a Excel con formato corporativo Unidossis."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return HttpResponse('openpyxl no está instalado. Ejecute: pip install openpyxl', status=500)

    perfil = request.user.perfil
    if perfil.rol in ['superadmin', 'admin_pqrs']:
        qs = Ticket.objects.all()
    else:
        qs = Ticket.objects.filter(regional=perfil.regional)

    # Filtros opcionales
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    regional_filtro = request.GET.get('regional')
    if fecha_inicio:
        qs = qs.filter(fecha_ingreso__date__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha_ingreso__date__lte=fecha_fin)
    if regional_filtro:
        qs = qs.filter(regional=regional_filtro)

    qs = qs.order_by('-fecha_ingreso')

    # ─ Crear libro de trabajo
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Reporte PQRS UNIDOSSIS'

    # ─ Colores corporativos
    AZUL_CORP = 'FF0F3460'
    ROJO_CORP = 'FFe63946'
    GRIS_HEADER = 'FF1E293B'
    GRIS_CLARO = 'FFF8FAFC'
    BLANCO = 'FFFFFFFF'

    # ─ Fila 1: Título corporativo
    ws.merge_cells('A1:O1')
    title_cell = ws['A1']
    title_cell.value = 'REPORTE DE PQRS — UNIDOSSIS S.A.S.'
    title_cell.font = Font(name='Calibri', size=14, bold=True, color=BLANCO)
    title_cell.fill = PatternFill('solid', fgColor=AZUL_CORP)
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 30

    # ─ Fila 2: Fecha del reporte
    ws.merge_cells('A2:O2')
    date_cell = ws['A2']
    date_cell.value = f'Generado el {timezone.now().strftime("%d/%m/%Y %H:%M")} | Por: {request.user.get_full_name() or request.user.username}'
    date_cell.font = Font(name='Calibri', size=10, color='FF64748B')
    date_cell.fill = PatternFill('solid', fgColor=GRIS_CLARO)
    date_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[2].height = 20

    # ─ Fila 3: Encabezados
    headers = [
        ('ID Caso', 12), ('Fecha Ingreso', 16), ('Tipo Solicitud', 16),
        ('Estado', 13), ('Criticidad', 14), ('Cliente / Institución', 28),
        ('Ciudad', 16), ('Solicitante', 22), ('Correo', 28),
        ('Regional', 18), ('Área / Proceso', 18), ('Línea de Servicio', 18),
        ('Tipificación', 24), ('Responsable', 20), ('Días Transcurridos', 10),
    ]

    thin = Side(style='thin', color='FFE2E8F0')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col_idx, (header_text, col_width) in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx)
        cell.value = header_text
        cell.font = Font(name='Calibri', size=10, bold=True, color=BLANCO)
        cell.fill = PatternFill('solid', fgColor=GRIS_HEADER)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border
        ws.column_dimensions[get_column_letter(col_idx)].width = col_width

    ws.row_dimensions[3].height = 35

    # ─ Mapas de labels
    tipo_map = dict(Ticket.TIPO_SOLICITUD_CHOICES)
    estado_map = dict(Ticket.STATUS_CHOICES)
    criticidad_map = dict(Ticket.CRITICIDAD_CHOICES)
    regional_map = dict(Ticket.REGIONAL_CHOICES)
    area_map = dict(Ticket.AREA_CHOICES)
    linea_map = dict(Ticket.LINEA_CHOICES)
    tipificacion_map = dict(Ticket.TIPIFICACION_CHOICES)

    # ─ Colores de estado
    COLOR_ESTADO = {
        'abierto': 'FF3B82F6',
        'revision': 'FFF59E0B',
        'resuelto': 'FF10B981',
        'cancelado': 'FF94A3B8',
    }
    COLOR_CRITICIDAD = {
        'critica': 'FFEF4444',
        'mayor': 'FFF97316',
        'menor': 'FFF59E0B',
        'informativa': 'FF10B981',
    }

    # ─ Datos
    for row_idx, ticket in enumerate(qs, start=4):
        fill_row = PatternFill('solid', fgColor=BLANCO if row_idx % 2 == 0 else 'FFF8FAFC')
        row_data = [
            ticket.ticket_id,
            ticket.fecha_ingreso.strftime('%d/%m/%Y %H:%M'),
            tipo_map.get(ticket.tipo_solicitud, ticket.tipo_solicitud or ''),
            estado_map.get(ticket.estado, ticket.estado or ''),
            criticidad_map.get(ticket.criticidad, ticket.criticidad or ''),
            ticket.entidad_cliente or ticket.institucion or '',
            ticket.ciudad or '',
            ticket.remitente_nombre or '',
            ticket.remitente_email or '',
            regional_map.get(ticket.regional, ticket.regional or ''),
            area_map.get(ticket.proceso, ticket.proceso or ''),
            linea_map.get(ticket.linea_servicio, ticket.linea_servicio or ''),
            tipificacion_map.get(ticket.tipificacion, ticket.tipificacion or ''),
            ticket.responsable or '',
            ticket.dias_transcurridos(),
        ]

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = Font(name='Calibri', size=9)
            cell.border = border
            cell.alignment = Alignment(vertical='center', wrap_text=False)
            cell.fill = fill_row

            # Color especial para estado
            if col_idx == 4 and ticket.estado in COLOR_ESTADO:
                cell.font = Font(name='Calibri', size=9, bold=True, color=BLANCO)
                cell.fill = PatternFill('solid', fgColor=COLOR_ESTADO[ticket.estado])
                cell.alignment = Alignment(horizontal='center', vertical='center')

            # Color especial para criticidad
            if col_idx == 5 and ticket.criticidad in COLOR_CRITICIDAD:
                cell.font = Font(name='Calibri', size=9, bold=True, color=BLANCO)
                cell.fill = PatternFill('solid', fgColor=COLOR_CRITICIDAD[ticket.criticidad])
                cell.alignment = Alignment(horizontal='center', vertical='center')

    ws.freeze_panes = 'A4'

    # ─ Generar respuesta
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'PQRS_UNIDOSSIS_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


# ─────────────────────────────────────────────────────────────
# ENCUESTA CSAT
# ─────────────────────────────────────────────────────────────

def encuesta_csat_view(request, token):
    """Vista pública para que el cliente responda la encuesta de satisfacción."""
    encuesta = get_object_or_404(EncuestaSatisfaccion, token=token)

    if encuesta.estado in ['satisfecho', 'insatisfecho']:
        return render(request, 'tickets/encuesta_ya_respondida.html', {'encuesta': encuesta})

    if request.method == 'POST':
        puntuacion = int(request.POST.get('puntuacion', 0))
        comentario = request.POST.get('comentario', '').strip()

        encuesta.puntuacion = puntuacion
        encuesta.comentario_cliente = comentario
        encuesta.fecha_respuesta = timezone.now()

        ticket = encuesta.ticket

        if puntuacion >= 4:
            # Satisfecho → cierre definitivo
            encuesta.estado = 'satisfecho'
            ticket.estado = 'resuelto'
            ticket.save()
            LogActividad.objects.create(
                ticket=ticket, usuario=None,
                accion=f'Encuesta CSAT respondida: SATISFECHO ({puntuacion}/5 ⭐)',
                detalle=f'Comentario: {comentario[:100]}' if comentario else 'Sin comentario'
            )
        else:
            # Insatisfecho → reabrir y alertar
            encuesta.estado = 'insatisfecho'
            ticket.estado = 'revision'
            ticket.save()
            LogActividad.objects.create(
                ticket=ticket, usuario=None,
                accion=f'🚨 Encuesta CSAT: INSATISFECHO ({puntuacion}/5 ⭐) — Ticket REABIERTO automáticamente',
                detalle=f'Comentario cliente: {comentario[:200]}' if comentario else 'Sin comentario'
            )
            # Notificar al equipo que el cliente está insatisfecho
            try:
                config = ConfiguracionSLA.objects.filter(activo=True).first()
                destinatarios = config.get_emails_vencido() if config else []
                if destinatarios:
                    send_mail(
                        subject=f'🚨 CSAT NEGATIVO — Ticket {ticket.ticket_id} reabierto automáticamente',
                        message=(
                            f'El cliente {ticket.remitente_nombre or ticket.remitente_email} '
                            f'respondió la encuesta CSAT con una puntuación de {puntuacion}/5.\n\n'
                            f'El ticket #{ticket.ticket_id} ha sido REABIERTO automáticamente y '
                            f'requiere revisión urgente.\n\n'
                            f'Comentario del cliente: {comentario or "(Sin comentario)"}\n\n'
                            f'— UNIDOSSIS PQRS · Sistema Automático'
                        ),
                        from_email='UNIDOSSIS PQRS <alertas@unidossis.com.co>',
                        recipient_list=destinatarios,
                        fail_silently=True,
                    )
            except Exception:
                pass

        encuesta.save()
        return render(request, 'tickets/encuesta_gracias.html', {
            'encuesta': encuesta,
            'satisfecho': encuesta.estado == 'satisfecho'
        })

    return render(request, 'tickets/encuesta_csat.html', {'encuesta': encuesta})


# ─────────────────────────────────────────────────────────────
# MONITOREO DEL SISTEMA
# ─────────────────────────────────────────────────────────────

@login_required
@rol_requerido('superadmin')
def monitoreo_view(request):
    """Panel de monitoreo: muestra logs de rendimiento y errores del sistema."""
    import os
    from pathlib import Path

    log_dir = Path(__file__).resolve().parent.parent / 'logs'

    def leer_ultimas_lineas(archivo, n=100):
        """Lee las últimas N líneas de un archivo de log."""
        ruta = log_dir / archivo
        if not ruta.exists():
            return []
        try:
            with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
                lineas = f.readlines()
            return [l.strip() for l in lineas[-n:] if l.strip()][::-1]  # Más reciente primero
        except Exception:
            return []

    log_rendimiento = leer_ultimas_lineas('rendimiento.log', 150)
    log_errores = leer_ultimas_lineas('errores.log', 100)

    # Estadísticas
    total_peticiones = len(log_rendimiento)
    peticiones_lentas = sum(1 for l in log_rendimiento if 'LENTO' in l)
    total_errores = len(log_errores)

    # Tamaño de la base de datos
    db_path = Path(__file__).resolve().parent.parent / 'db.sqlite3'
    if db_path.exists():
        tamano_bytes = db_path.stat().st_size
        if tamano_bytes > 1024 * 1024:
            tamano_db = f'{tamano_bytes / (1024*1024):.1f} MB'
        else:
            tamano_db = f'{tamano_bytes / 1024:.0f} KB'
    else:
        tamano_db = 'N/A'

    return render(request, 'tickets/monitoreo.html', {
        'log_rendimiento': log_rendimiento,
        'log_errores': log_errores,
        'total_peticiones': total_peticiones,
        'peticiones_lentas': peticiones_lentas,
        'total_errores': total_errores,
        'tamano_db': tamano_db,
        'perfil': request.user.perfil,
        'nav_active': 'monitoreo',
    })


@login_required
@rol_requerido('superadmin')
def descargar_log_view(request, tipo):
    """Descarga un archivo de log específico."""
    from pathlib import Path

    log_dir = Path(__file__).resolve().parent.parent / 'logs'
    archivos_permitidos = {
        'rendimiento': 'rendimiento.log',
        'errores': 'errores.log',
    }

    if tipo not in archivos_permitidos:
        return HttpResponse('Archivo no válido.', status=400)

    ruta = log_dir / archivos_permitidos[tipo]
    if not ruta.exists():
        return HttpResponse(f'El archivo {archivos_permitidos[tipo]} aún no tiene registros.', status=404)

    with open(ruta, 'r', encoding='utf-8', errors='replace') as f:
        contenido = f.read()

    fecha = timezone.now().strftime('%Y-%m-%d_%H%M')
    response = HttpResponse(contenido, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="unidossis_{tipo}_{fecha}.log"'
    return response


@login_required
@rol_requerido('superadmin')
def descargar_respaldo_db_view(request):
    """Descarga un respaldo completo de la base de datos SQLite."""
    from pathlib import Path

    db_path = Path(__file__).resolve().parent.parent / 'db.sqlite3'
    if not db_path.exists():
        return HttpResponse('Base de datos no encontrada.', status=404)

    fecha = timezone.now().strftime('%Y-%m-%d_%H%M')
    with open(db_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='application/x-sqlite3')
        response['Content-Disposition'] = f'attachment; filename="unidossis_respaldo_{fecha}.sqlite3"'
    return response


