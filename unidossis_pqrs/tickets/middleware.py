"""
Middleware de monitoreo de rendimiento y errores.
Registra el tiempo de respuesta de cada petición y errores no capturados.
Los reportes se guardan en logs/rendimiento.log y logs/unidossis.log
"""
import time
import logging
import traceback

logger_rendimiento = logging.getLogger('unidossis.rendimiento')
logger_errores = logging.getLogger('unidossis.errores')


class MonitorRendimientoMiddleware:
    """
    Mide el tiempo de respuesta de cada petición HTTP.
    Registra peticiones lentas (>2s) como WARNING y todas como DEBUG.
    """

    UMBRAL_LENTO = 2.0  # segundos — más de 2s se marca como lento

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.time()
        request._inicio_form = inicio  # Disponible para context processors y templates

        response = self.get_response(request)

        duracion = time.time() - inicio
        status = response.status_code
        metodo = request.method
        ruta = request.path
        usuario = request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anónimo'

        # Ignorar archivos estáticos
        if ruta.startswith('/static/') or ruta.startswith('/media/'):
            return response

        # Log de rendimiento
        msg = f'{metodo} {ruta} → {status} | {duracion:.2f}s | usuario: {usuario}'

        if duracion > self.UMBRAL_LENTO:
            logger_rendimiento.warning(f'⚠️ LENTO: {msg}')
        elif status >= 500:
            logger_rendimiento.error(f'❌ ERROR {status}: {msg}')
        elif status >= 400:
            logger_rendimiento.info(f'⚡ {msg}')
        else:
            logger_rendimiento.debug(msg)

        return response

    def process_exception(self, request, exception):
        """Captura excepciones no manejadas, las clasifica con códigos y renderiza error 500 premium."""
        ruta = request.path
        usuario = request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anónimo'
        error_type = type(exception).__name__
        error_msg = str(exception)

        # ── Clasificación de errores ──
        error_code = self._classify_error(error_type, error_msg)

        logger_errores.error(
            f'💥 [{error_code}] EXCEPCIÓN en {ruta} | usuario: {usuario} | '
            f'{error_type}: {error_msg}\n'
            f'{traceback.format_exc()}'
        )

        # Renderizar página 500 premium con catálogo
        from django.template.loader import render_to_string
        from django.http import HttpResponseServerError
        from django.utils import timezone
        try:
            html = render_to_string('500.html', {
                'error_code': error_code,
                'error_type': error_type,
                'error_message': error_msg[:200],
                'error_path': ruta,
                'error_time': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'error_detail': True,
            })
            return HttpResponseServerError(html)
        except Exception:
            return None  # Fallback a Django default si falla el render

    @staticmethod
    def _classify_error(error_type, error_msg):
        """Clasifica el error en un código de catálogo."""
        msg_lower = error_msg.lower()

        # DB — Base de datos
        if 'OperationalError' in error_type:
            if 'no such column' in msg_lower:
                return 'DB-001'
            elif 'no such table' in msg_lower:
                return 'DB-002'
            elif 'database is locked' in msg_lower:
                return 'DB-003'
            return 'DB-099'

        if 'IntegrityError' in error_type:
            return 'DB-004'

        # TPL — Templates
        if 'TemplateSyntaxError' in error_type:
            return 'TPL-001'
        if 'TemplateDoesNotExist' in error_type:
            return 'TPL-002'

        # AUTH — Autenticación
        if 'PermissionDenied' in error_type:
            return 'AUTH-001'

        # NET — Red / API
        if 'ConnectionError' in error_type or 'Timeout' in error_type:
            return 'NET-001'

        # FILE — Archivos
        if 'FileNotFoundError' in error_type or 'SuspiciousFileOperation' in error_type:
            return 'FILE-001'

        # CFG — Configuración
        if 'ImproperlyConfigured' in error_type:
            return 'CFG-001'

        # General
        if 'ValueError' in error_type:
            return 'SYS-001'
        if 'KeyError' in error_type:
            return 'SYS-002'
        if 'AttributeError' in error_type:
            return 'SYS-003'

        return 'SYS-099'


class SimulacionRolMiddleware:
    """
    Middleware de 'View As' / Role Impersonation — solo para superadmin.

    Cuando el superadmin activa una simulación (session['simular_rol']),
    este middleware parchea temporalmente perfil.rol en memoria para que
    TODAS las vistas y templates muestren la interfaz del rol simulado.

    Seguridad:
    - Solo funciona si el usuario real es superadmin.
    - Nunca persiste el cambio de rol en la base de datos.
    - Protege contra saves accidentales sobreescribiendo .save() temporalmente.
    """

    ROLES_SIMULABLES = ['admin_pqrs', 'director_regional', 'agente', 'cliente']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Flags por defecto
        request.simulacion_activa = False
        request.rol_original = None
        request.rol_simulado = None
        request.cliente_simulado = None

        # Solo actuar si hay usuario autenticado con perfil superadmin y simulación en sesión
        if (request.user.is_authenticated
                and hasattr(request.user, 'perfil')
                and request.user.perfil.rol == 'superadmin'):

            rol_simulado = request.session.get('simular_rol')

            if rol_simulado and rol_simulado in self.ROLES_SIMULABLES:
                perfil = request.user.perfil
                request.simulacion_activa = True
                request.rol_original = 'superadmin'
                request.rol_simulado = rol_simulado

                # Parchear el rol en la instancia (NO en la BD)
                perfil.rol = rol_simulado

                # ── Fix Director Regional: parchear la regional desde sesión ──
                if rol_simulado == 'director_regional':
                    regional_sim = request.session.get('simular_regional', '')
                    perfil.regional = regional_sim

                # ── Fix Cliente: inyectar un cliente mock para poder navegar el portal ──
                if rol_simulado == 'cliente':
                    from .models import Cliente
                    cliente_sim_id = request.session.get('simular_cliente_id')
                    cliente_mock = None
                    if cliente_sim_id:
                        try:
                            cliente_mock = Cliente.objects.get(pk=cliente_sim_id)
                        except Cliente.DoesNotExist:
                            pass
                    if not cliente_mock:
                        # Usar el primer cliente con tickets disponible
                        cliente_mock = Cliente.objects.filter(tickets__isnull=False).first()
                        if not cliente_mock:
                            cliente_mock = Cliente.objects.first()
                    # Inyectar en el perfil (solo en memoria)
                    perfil.cliente = cliente_mock
                    request.cliente_simulado = cliente_mock

                # Proteger contra saves accidentales que podrían persistir el rol falso
                _original_save = perfil.save
                def _safe_save(*args, **kwargs):
                    perfil.rol = 'superadmin'  # restaurar antes de cualquier save
                    _original_save(*args, **kwargs)
                    perfil.rol = rol_simulado  # re-aplicar después del save
                perfil.save = _safe_save

        response = self.get_response(request)

        # Restaurar rol real al terminar (por si el objeto persiste en caché)
        if request.simulacion_activa and hasattr(request.user, 'perfil'):
            request.user.perfil.rol = 'superadmin'

        return response
