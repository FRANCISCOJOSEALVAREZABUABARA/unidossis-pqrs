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
                else:
                    # Superadmin, admin, director, agente → siempre al dashboard
                    return redirect('dashboard')
            except PerfilUsuario.DoesNotExist:
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


def recuperar_password_view(request):
    """Flujo híbrido de recuperación de contraseña.
    1. Verifica que el email existe en la BD
    2. Si SMTP configurado → envía email con token de Django
    3. Si SMTP no configurado → crea solicitud para el admin
    """
    resultado = None

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()

        if not email or '@' not in email:
            resultado = {'tipo': 'error', 'texto': 'Por favor ingrese un correo electrónico válido.'}
        else:
            # Buscar usuario por email (en User.email, Cliente.email_principal, o Cliente.emails_adicionales)
            user_encontrado = None

            # 1. Buscar en User.email
            user_encontrado = User.objects.filter(email__iexact=email, is_active=True).first()

            # 2. Si no, buscar en Cliente.email_principal → su User asociado
            if not user_encontrado:
                cliente = Cliente.objects.filter(email_principal__iexact=email, activo=True, user__isnull=False).first()
                if cliente and cliente.user:
                    user_encontrado = cliente.user

            # 3. Si no, buscar en Cliente.emails_adicionales
            if not user_encontrado:
                for c in Cliente.objects.filter(activo=True, user__isnull=False):
                    if c.emails_adicionales:
                        emails_add = [e.strip().lower() for e in c.emails_adicionales.split(',')]
                        if email in emails_add:
                            user_encontrado = c.user
                            break

            if not user_encontrado:
                resultado = {
                    'tipo': 'no_encontrado',
                    'texto': 'El correo ingresado no está registrado en el sistema. '
                             'Puede solicitar ayuda al administrador completando el formulario a continuación.'
                }
            else:
                # ── Verificar si SMTP está configurado ──
                from .notificaciones import _smtp_configurado
                if _smtp_configurado():
                    # Opción A: Enviar email con token de reset
                    from django.contrib.auth.tokens import default_token_generator
                    from django.utils.http import urlsafe_base64_encode
                    from django.utils.encoding import force_bytes

                    token = default_token_generator.make_token(user_encontrado)
                    uid = urlsafe_base64_encode(force_bytes(user_encontrado.pk))

                    if request:
                        base_url = request.build_absolute_uri('/')[:-1]
                    else:
                        base_url = 'https://unidossis.pythonanywhere.com'

                    reset_url = f'{base_url}/recuperar-password/confirmar/{uid}/{token}/'

                    send_mail(
                        subject='🔑 Restablecer contraseña — Unidossis PQRS',
                        message=(
                            f'Hola {user_encontrado.get_full_name() or user_encontrado.username},\n\n'
                            f'Recibimos una solicitud para restablecer su contraseña.\n\n'
                            f'Haga clic en el siguiente enlace para crear una nueva contraseña:\n'
                            f'{reset_url}\n\n'
                            f'Este enlace es válido por 24 horas y solo puede usarse una vez.\n\n'
                            f'Si usted no solicitó este cambio, ignore este mensaje.\n\n'
                            f'— Unidossis PQRS'
                        ),
                        from_email=None,  # Usa DEFAULT_FROM_EMAIL
                        recipient_list=[email],
                        fail_silently=False,
                    )

                    LogActividad.objects.create(
                        usuario=user_encontrado,
                        accion='Solicitud de restablecimiento de contraseña (email enviado)',
                        detalle=f'Email enviado a: {email}'
                    )

                    resultado = {
                        'tipo': 'email_enviado',
                        'texto': f'Hemos enviado un enlace de recuperación al correo {email}. '
                                 'Revise su bandeja de entrada (y la carpeta de spam).'
                    }
                else:
                    # Opción B: Crear solicitud para el admin
                    ip = _get_client_ip(request)
                    SolicitudResetPassword.objects.create(
                        user=user_encontrado,
                        email_ingresado=email,
                        ip=ip,
                    )

                    LogActividad.objects.create(
                        usuario=user_encontrado,
                        accion='Solicitud de restablecimiento de contraseña (pendiente admin)',
                        detalle=f'Email: {email} | IP: {ip}'
                    )

                    resultado = {
                        'tipo': 'solicitud_admin',
                        'texto': 'Su solicitud ha sido registrada. El administrador del sistema '
                                 'le asignará una nueva contraseña temporal. '
                                 'Será contactado por el equipo de soporte.'
                    }

    # Si es solicitud al admin cuando email NO fue encontrado
    if request.method == 'POST' and request.POST.get('accion') == 'solicitar_admin':
        nombre = request.POST.get('nombre_completo', '').strip()
        email_contacto = request.POST.get('email_contacto', '').strip()
        username_recordado = request.POST.get('username_recordado', '').strip()
        detalle = request.POST.get('detalle', '').strip()

        if nombre and email_contacto:
            LogActividad.objects.create(
                usuario=None,
                accion='Solicitud de ayuda con acceso (usuario no encontrado)',
                detalle=f'Nombre: {nombre} | Email: {email_contacto} | '
                        f'Username recordado: {username_recordado} | Detalle: {detalle}'
            )
            resultado = {
                'tipo': 'solicitud_admin',
                'texto': 'Su solicitud de ayuda ha sido registrada exitosamente. '
                         'El administrador se comunicará con usted al correo proporcionado.'
            }

    return render(request, 'tickets/recuperar_password.html', {'resultado': resultado})


def recuperar_password_confirm_view(request, uidb64, token):
    """Confirma el token de reset y permite crear nueva contraseña."""
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_decode

    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            error = None
            if len(new_password) < 8:
                error = 'La contraseña debe tener al menos 8 caracteres.'
            elif new_password != confirm_password:
                error = 'Las contraseñas no coinciden.'

            if error:
                return render(request, 'tickets/recuperar_password_confirm.html', {
                    'valid': True, 'error': error, 'uidb64': uidb64, 'token': token
                })

            user.set_password(new_password)
            user.save()

            # Desactivar flag de cambio obligatorio si existe
            if hasattr(user, 'perfil'):
                user.perfil.debe_cambiar_password = False
                user.perfil.save(update_fields=['debe_cambiar_password'])

            LogActividad.objects.create(
                usuario=user,
                accion='Contraseña restablecida exitosamente via enlace de recuperación',
            )

            return render(request, 'tickets/recuperar_password_completado.html')

        return render(request, 'tickets/recuperar_password_confirm.html', {
            'valid': True, 'uidb64': uidb64, 'token': token
        })
    else:
        return render(request, 'tickets/recuperar_password_confirm.html', {'valid': False})


def acceso_denegado_view(request):
    """Vista genérica para errores de permisos."""
    mensaje = request.GET.get('mensaje', 'No tiene permisos para acceder a esta sección.')
    return render(request, 'tickets/acceso_denegado.html', {'mensaje': mensaje})


