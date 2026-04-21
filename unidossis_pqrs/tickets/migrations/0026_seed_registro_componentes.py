"""
Migración de datos — Poblar RegistroComponente desde FORM_REGISTRY
==================================================================
Esta migración es idempotente: usa get_or_create para no duplicar registros.
Si el componente ya existe (por código), lo actualiza con los datos del registry.
"""
from django.db import migrations


FORM_REGISTRY_SEED = {
    'public_portal': {
        'code': 'F-01', 'name': 'PORTAL-PQRS',
        'full_name': 'Portal de Radicación PQRS', 'version': 'v1.0.0',
        'tablas': 'Ticket, AdjuntoTicket',
        'descripcion': 'Formulario público para que las instituciones clientes radiquen peticiones, quejas, reclamos y sugerencias con evidencia adjunta.',
        'tipo': 'formulario',
    },
    'encuesta_csat': {
        'code': 'F-11', 'name': 'ENCUESTA-CSAT',
        'full_name': 'Encuesta de Satisfacción CSAT', 'version': 'v1.0.0',
        'tablas': 'EncuestaSatisfaccion',
        'descripcion': 'Encuesta post-cierre enviada automáticamente al cliente para medir su nivel de satisfacción con la resolución del caso.',
        'tipo': 'formulario',
    },
    'login': {
        'code': 'F-02', 'name': 'LOGIN',
        'full_name': 'Inicio de Sesión', 'version': 'v1.1.0',
        'tablas': 'auth_user, IntentoLogin',
        'descripcion': 'Pantalla de inicio de sesión con control de intentos fallidos y registro de accesos.',
        'tipo': 'formulario',
    },
    'cambiar_password': {
        'code': 'F-03', 'name': 'CAMBIAR-PWD',
        'full_name': 'Cambio de Contraseña (Perfil)', 'version': 'v1.0.0',
        'tablas': 'auth_user',
        'descripcion': 'Permite al usuario autenticado cambiar su contraseña actual desde su perfil.',
        'tipo': 'formulario',
    },
    'recuperar_password': {
        'code': 'F-05', 'name': 'RECUPERAR-PWD',
        'full_name': 'Recuperación de Contraseña', 'version': 'v1.0.0',
        'tablas': 'SolicitudResetPassword',
        'descripcion': 'Formulario público para solicitar un enlace de restablecimiento de contraseña vía correo electrónico.',
        'tipo': 'formulario',
    },
    'recuperar_password_confirm': {
        'code': 'F-06', 'name': 'CONFIRMAR-PWD',
        'full_name': 'Confirmación de Nueva Contraseña', 'version': 'v1.0.0',
        'tablas': 'auth_user, SolicitudResetPassword',
        'descripcion': 'Página donde el usuario define su nueva contraseña usando el token enviado por correo.',
        'tipo': 'formulario',
    },
    'ticket_detail': {
        'code': 'F-07', 'name': 'DETALLE-TICKET',
        'full_name': 'Edición / Gestión de Ticket PQRS', 'version': 'v2.1.0',
        'tablas': 'Ticket, Comentario, AdjuntoTicket, LogActividad',
        'descripcion': 'Vista principal de gestión de un caso PQRS: cambio de estado, asignación, respuesta oficial, adjuntos y comentarios internos.',
        'tipo': 'formulario',
    },
    'crear_pqrs_manual': {
        'code': 'F-07B', 'name': 'CREAR-TICKET-MANUAL',
        'full_name': 'Creación Manual de Ticket', 'version': 'v1.0.0',
        'tablas': 'Ticket, AdjuntoTicket',
        'descripcion': 'Permite a un agente o administrador crear un ticket PQRS manualmente en nombre de un cliente.',
        'tipo': 'formulario',
    },
    'gestionar_clientes': {
        'code': 'F-08', 'name': 'GESTIONAR-CLIENTES',
        'full_name': 'Gestión de Clientes e Instituciones', 'version': 'v2.0.0',
        'tablas': 'Cliente, auth_user, Perfil',
        'descripcion': 'Consola para crear, editar e inactivar instituciones clientes, habilitar accesos al portal y gestionar usuarios internos.',
        'tipo': 'formulario',
    },
    'configurar_sla': {
        'code': 'F-10', 'name': 'CONFIG-SLA',
        'full_name': 'Configuración de SLA y Alertas', 'version': 'v1.2.0',
        'tablas': 'ConfiguracionSLA, AlertaSLA',
        'descripcion': 'Define los tiempos máximos de respuesta por tipo de solicitud y configura las alertas automáticas de vencimiento.',
        'tipo': 'formulario',
    },
    'consola_tabla': {
        'code': 'F-12', 'name': 'CONSOLA-TABLAS',
        'full_name': 'Consola — Tablas Maestras CRUD', 'version': 'v1.0.0',
        'tablas': 'Ciudad, Regional, LineaServicio, TipificacionPQRS',
        'descripcion': 'CRUD genérico para mantener las tablas maestras del sistema: ciudades, regionales, líneas de servicio y tipificaciones.',
        'tipo': 'formulario',
    },
    'consola_perfil_detalle': {
        'code': 'F-13', 'name': 'CONSOLA-PERFIL',
        'full_name': 'Consola — Edición de Perfil de Usuario', 'version': 'v1.1.0',
        'tablas': 'Perfil, auth_user',
        'descripcion': 'Edición detallada del perfil de un usuario: datos personales, rol asignado, regional y foto de perfil.',
        'tipo': 'formulario',
    },
    'consola_permisos': {
        'code': 'F-13B', 'name': 'CONSOLA-PERMISOS',
        'full_name': 'Consola — Matriz de Permisos por Rol', 'version': 'v1.0.0',
        'tablas': 'PermisoRol',
        'descripcion': 'Configuración granular de permisos por rol: define qué acciones puede ejecutar cada perfil del sistema.',
        'tipo': 'formulario',
    },
    'dashboard': {
        'code': 'V-01', 'name': 'DASHBOARD',
        'full_name': 'Dashboard de Tickets', 'version': 'v3.0.0',
        'tablas': 'Ticket, AlertaSLA, LogActividad',
        'descripcion': 'Panel principal con KPIs, tabla de tickets con filtros avanzados, búsqueda inteligente y resumen por estados.',
        'tipo': 'vista',
    },
    'portal_cliente_dashboard': {
        'code': 'V-02', 'name': 'PORTAL-DASHBOARD',
        'full_name': 'Dashboard del Cliente', 'version': 'v2.0.0',
        'tablas': 'Ticket, EncuestaSatisfaccion',
        'descripcion': 'Portal del cliente con listado de sus tickets, resumen IA y acceso a la respuesta oficial y documentos adjuntos.',
        'tipo': 'vista',
    },
    'portal_cliente_analytics': {
        'code': 'V-03', 'name': 'PORTAL-ANALYTICS',
        'full_name': 'Analíticas del Cliente', 'version': 'v1.0.0',
        'tablas': 'Ticket, EncuestaSatisfaccion',
        'descripcion': 'Gráficas y métricas de rendimiento de los tickets del cliente: tiempos de resolución, satisfacción y volumen.',
        'tipo': 'vista',
    },
    'reportes': {
        'code': 'V-04', 'name': 'REPORTES',
        'full_name': 'Módulo de Reportes y Exportación', 'version': 'v1.1.0',
        'tablas': 'Ticket, Cliente, EncuestaSatisfaccion',
        'descripcion': 'Generación de reportes exportables (Excel/PDF) con filtros por fecha, regional, tipificación y estado.',
        'tipo': 'vista',
    },
    'monitoreo': {
        'code': 'V-05', 'name': 'MONITOREO',
        'full_name': 'Monitor del Sistema', 'version': 'v1.2.0',
        'tablas': 'IntentoLogin, LogActividad',
        'descripcion': 'Panel de salud del sistema: uso de CPU/memoria, estado de la BD, estadísticas de acceso y errores recientes.',
        'tipo': 'vista',
    },
    'consola_central': {
        'code': 'V-06', 'name': 'CONSOLA-CENTRAL',
        'full_name': 'Consola Central de Administración', 'version': 'v2.1.0',
        'tablas': 'Todas las tablas (lectura)',
        'descripcion': 'Hub de administración con KPIs del sistema, acceso directo a módulos y timeline de actividad reciente.',
        'tipo': 'vista',
    },
    'consola_perfiles': {
        'code': 'V-07', 'name': 'CONSOLA-PERFILES',
        'full_name': 'Consola — Perfiles de Usuario', 'version': 'v1.0.0',
        'tablas': 'Perfil, auth_user',
        'descripcion': 'Directorio de todos los usuarios registrados con tarjeta de perfil, rol y acciones rápidas.',
        'tipo': 'vista',
    },
    'consola_auditoria': {
        'code': 'V-08', 'name': 'CONSOLA-AUDITORIA',
        'full_name': 'Consola — Centro de Auditoría', 'version': 'v1.0.0',
        'tablas': 'LogActividad, IntentoLogin, SolicitudResetPassword',
        'descripcion': 'Registro cronológico de todas las acciones del sistema: cambios de estado, accesos, intentos fallidos y resets.',
        'tipo': 'vista',
    },
    'control_cambios': {
        'code': 'V-09', 'name': 'CONTROL-CAMBIOS',
        'full_name': 'Control de Cambios (Git)', 'version': 'v1.0.0',
        'tablas': 'N/A (Git)',
        'descripcion': 'Visualización del historial de commits Git, comparación de archivos modificados y reversión controlada.',
        'tipo': 'vista',
    },
    'consola_inventario': {
        'code': 'V-10', 'name': 'CONSOLA-INVENTARIO',
        'full_name': 'Registro Central de Componentes', 'version': 'v1.0.0',
        'tablas': 'RegistroComponente',
        'descripcion': 'Inventario completo de todos los formularios, vistas y módulos del sistema con versión y tablas conectadas.',
        'tipo': 'vista',
    },
}


def seed_componentes(apps, schema_editor):
    """Carga los componentes del FORM_REGISTRY en RegistroComponente. Idempotente."""
    RegistroComponente = apps.get_model('tickets', 'RegistroComponente')
    for url_name, data in FORM_REGISTRY_SEED.items():
        obj, created = RegistroComponente.objects.get_or_create(
            code=data['code'],
            defaults={
                'name': data['name'],
                'full_name': data['full_name'],
                'version': data['version'],
                'url_name': url_name,
                'tablas': data['tablas'],
                'descripcion': data['descripcion'],
                'tipo': data['tipo'],
                'activo': True,
            }
        )
        if not created:
            # Actualizar si ya existe
            obj.name = data['name']
            obj.full_name = data['full_name']
            obj.version = data['version']
            obj.url_name = url_name
            obj.tablas = data['tablas']
            obj.descripcion = data['descripcion']
            obj.tipo = data['tipo']
            obj.activo = True
            obj.save()


def unseed_componentes(apps, schema_editor):
    """Reversa: elimina los registros sembrados por esta migración."""
    RegistroComponente = apps.get_model('tickets', 'RegistroComponente')
    codes = [d['code'] for d in FORM_REGISTRY_SEED.values()]
    RegistroComponente.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0025_rol_personalizado'),
    ]

    operations = [
        migrations.RunPython(seed_componentes, unseed_componentes),
    ]
