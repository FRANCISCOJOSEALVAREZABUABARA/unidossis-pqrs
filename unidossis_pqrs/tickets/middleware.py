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
        """Captura excepciones no manejadas y las registra."""
        ruta = request.path
        usuario = request.user.username if hasattr(request, 'user') and request.user.is_authenticated else 'anónimo'

        logger_errores.error(
            f'💥 EXCEPCIÓN en {ruta} | usuario: {usuario} | '
            f'{type(exception).__name__}: {str(exception)}\n'
            f'{traceback.format_exc()}'
        )
        return None  # Deja que Django maneje el error normalmente
