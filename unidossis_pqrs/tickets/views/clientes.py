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
        rol__in=['admin_pqrs', 'director_regional', 'agente']
    ).select_related('user').order_by('user__first_name')

    ROL_CHOICES_INTERNOS = [
        ('admin_pqrs', 'Administrador PQRS'),
        ('director_regional', 'Director Regional'),
        ('agente', 'Agente / Consultor'),
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


