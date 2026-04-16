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
