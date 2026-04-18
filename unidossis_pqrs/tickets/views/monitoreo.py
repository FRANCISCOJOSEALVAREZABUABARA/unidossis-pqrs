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
import subprocess
import os

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


@login_required
@rol_requerido('superadmin')
def control_cambios_view(request):
    """Panel de control de cambios: muestra historial de commits, estado de sincronización
    con producción y permite revertir cambios específicos."""
    import subprocess
    from pathlib import Path

    repo_dir = Path(__file__).resolve().parent.parent.parent  # raíz del repo

    def run_git(args, cwd=None):
        """Ejecuta un comando git y retorna la salida."""
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=str(cwd or repo_dir),
                capture_output=True, text=True, timeout=15,
                encoding='utf-8', errors='replace'
            )
            return result.stdout.strip()
        except Exception:
            return ''

    # Obtener commits recientes (últimos 30)
    log_output = run_git([
        'log', '--pretty=format:%H||%h||%an||%ad||%s', '--date=format:%d/%m/%Y %H:%M', '-30'
    ])

    commits = []
    for line in (log_output.split('\n') if log_output else []):
        parts = line.split('||')
        if len(parts) >= 5:
            msg = parts[4]
            # Detectar tipo de commit por prefijo convencional (Conventional Commits spec)
            prefix_type = 'other'
            msg_lower = msg.lower().strip()
            if msg_lower.startswith('feat') or '✨' in msg:
                prefix_type = 'feat'
            elif msg_lower.startswith('fix') or '🐛' in msg or 'fix:' in msg_lower:
                prefix_type = 'fix'
            elif msg_lower.startswith('docs') or '📝' in msg:
                prefix_type = 'docs'
            elif msg_lower.startswith('style') or '💄' in msg:
                prefix_type = 'style'
            elif msg_lower.startswith('refactor') or '♻️' in msg:
                prefix_type = 'refactor'
            elif msg_lower.startswith('perf') or '⚡' in msg:
                prefix_type = 'perf'
            elif msg_lower.startswith('test') or '✅' in msg:
                prefix_type = 'test'
            elif msg_lower.startswith(('ci', 'build', 'config')) or '👷' in msg:
                prefix_type = 'ci'
            elif msg_lower.startswith('chore') or '🔧' in msg:
                prefix_type = 'chore'
            elif msg_lower.startswith('revert'):
                prefix_type = 'revert'

            commits.append({
                'hash': parts[0],
                'hash_short': parts[1],
                'author': parts[2],
                'date': parts[3],
                'message': msg,
                'prefix_type': prefix_type,
                'is_in_prod': False,  # Se actualiza abajo
            })

    # Comparar con origin/main para detectar qué está en producción
    commits_ahead = 0
    try:
        # Fetch silencioso para actualizar la referencia remota
        run_git(['fetch', '--quiet'])
        ahead_output = run_git(['rev-list', '--count', 'origin/main..HEAD'])
        commits_ahead = int(ahead_output) if ahead_output.isdigit() else 0

        # Obtener el hash del último commit en producción
        prod_hash = run_git(['rev-parse', 'origin/main'])

        # Marcar commits que ya están en producción
        for i, commit in enumerate(commits):
            if i >= commits_ahead:
                commit['is_in_prod'] = True
    except Exception:
        pass

    # Estado de sincronización
    sync_status = 'synced' if commits_ahead == 0 else 'ahead'

    # Cambios pendientes (no commiteados)
    status_output = run_git(['status', '--short'])
    cambios_pendientes = [l.strip() for l in status_output.split('\n') if l.strip()] if status_output else []

    # Archivos modificados localmente
    archivos_modificados = len(cambios_pendientes)

    # Fecha del último commit
    ultimo_commit_fecha = commits[0]['date'].split(' ')[0] if commits else 'N/A'

    # ── Versión actual del proyecto ──────────────────────────
    version_actual = 'v1.0.0'
    try:
        from tickets import __version__
        version_actual = f'v{__version__}'
    except Exception:
        pass

    # ── Leer CHANGELOG.md (primeras secciones) ──────────────
    changelog_preview = ''
    changelog_path = repo_dir / 'CHANGELOG.md'
    if changelog_path.exists():
        try:
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog_preview = f.read(3000)  # Primeras 3000 chars
        except Exception:
            changelog_preview = ''

    # ── Releases/Tags del repositorio ───────────────────────
    tags_output = run_git(['tag', '-l', '--sort=-version:refname', '--format=%(refname:short)|||%(creatordate:short)|||%(subject)'])
    releases = []
    for line in (tags_output.split('\n') if tags_output else []):
        parts = line.split('|||')
        if parts and parts[0].strip():
            releases.append({
                'tag': parts[0].strip(),
                'fecha': parts[1].strip() if len(parts) > 1 else '',
                'descripcion': parts[2].strip() if len(parts) > 2 else '',
            })

    # ── Estado del último CI run (desde GitHub Actions API) ─
    # Leemos el estado via requests a la API pública del repo
    ci_status = 'unknown'
    ci_url = 'https://github.com/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/actions'
    try:
        import urllib.request
        api_url = 'https://api.github.com/repos/FRANCISCOJOSEALVAREZABUABARA/unidossis-pqrs/actions/runs?branch=main&per_page=1'
        req = urllib.request.Request(api_url, headers={'User-Agent': 'UnidossisPQRS/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json as _json
            data = _json.loads(resp.read())
            if data.get('workflow_runs'):
                run = data['workflow_runs'][0]
                ci_status = run.get('conclusion') or run.get('status', 'unknown')
                ci_url = run.get('html_url', ci_url)
    except Exception:
        pass  # No bloquear si GitHub no responde

    context = {
        'commits': commits,
        'total_commits': len(commits),
        'commits_ahead': commits_ahead,
        'sync_status': sync_status,
        'cambios_pendientes': cambios_pendientes,
        'archivos_modificados': archivos_modificados,
        'ultimo_commit_fecha': ultimo_commit_fecha,
        'version_actual': version_actual,
        'changelog_preview': changelog_preview,
        'releases': releases,
        'ci_status': ci_status,
        'ci_url': ci_url,
        'perfil': request.user.perfil,
        'nav_active': 'control_cambios',
    }
    return render(request, 'tickets/control_cambios.html', context)


    def run_git(args, cwd=None):
        """Ejecuta un comando git y retorna la salida."""
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=str(cwd or repo_dir),
                capture_output=True, text=True, timeout=15,
                encoding='utf-8', errors='replace'
            )
            return result.stdout.strip()
        except Exception:
            return ''


@login_required
@rol_requerido('superadmin')
def api_detalle_commit(request, commit_hash):
    """Retorna los archivos modificados en un commit específico (vía AJAX)."""
    import subprocess
    from pathlib import Path

    repo_dir = Path(__file__).resolve().parent.parent.parent

    # Validar hash (seguridad)
    if not all(c in '0123456789abcdefABCDEF' for c in commit_hash):
        return JsonResponse({'error': 'Hash inválido.'}, status=400)

    try:
        result = subprocess.run(
            ['git', 'diff-tree', '--no-commit-id', '-r', '--name-status', commit_hash],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        files = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    files.append({
                        'status': parts[0][0],  # M, A, D, R
                        'path': parts[-1],
                    })
        return JsonResponse({'files': files})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@rol_requerido('superadmin')
def api_diff_commit(request, commit_hash):
    """Retorna el diff de un commit específico (vía AJAX)."""
    import subprocess
    from pathlib import Path

    repo_dir = Path(__file__).resolve().parent.parent.parent

    # Validar hash
    if not all(c in '0123456789abcdefABCDEF' for c in commit_hash):
        return JsonResponse({'error': 'Hash inválido.'}, status=400)

    try:
        result = subprocess.run(
            ['git', 'diff', f'{commit_hash}~1', commit_hash, '--stat=120', '--no-color'],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        # También obtener diff con contexto limitado
        diff_result = subprocess.run(
            ['git', 'diff', f'{commit_hash}~1', commit_hash, '--no-color', '-U3'],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        diff_lines = diff_result.stdout.split('\n')[:500]  # Limitar a 500 líneas
        return JsonResponse({'diff': diff_lines, 'stat': result.stdout})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@rol_requerido('superadmin')
def api_revertir_commit(request, commit_hash):
    """Revierte un commit específico creando un nuevo commit de reversión.
    Solo funciona para commits que no están en producción."""
    import subprocess
    from pathlib import Path

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)

    repo_dir = Path(__file__).resolve().parent.parent.parent

    # Validar hash
    if not all(c in '0123456789abcdefABCDEF' for c in commit_hash):
        return JsonResponse({'error': 'Hash inválido.'}, status=400)

    try:
        # Verificar que el commit no está en producción
        ahead_output = subprocess.run(
            ['git', 'rev-list', '--count', 'origin/main..HEAD'],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        commits_ahead = int(ahead_output.stdout.strip()) if ahead_output.stdout.strip().isdigit() else 0

        local_commits = subprocess.run(
            ['git', 'rev-list', 'origin/main..HEAD'],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10,
            encoding='utf-8', errors='replace'
        )
        local_hashes = local_commits.stdout.strip().split('\n') if local_commits.stdout.strip() else []

        if commit_hash not in local_hashes:
            return JsonResponse({
                'success': False,
                'error': 'Este commit ya está en producción y no se puede revertir desde aquí.'
            })

        # Ejecutar revert
        result = subprocess.run(
            ['git', 'revert', '--no-edit', commit_hash],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=30,
            encoding='utf-8', errors='replace'
        )

        if result.returncode == 0:
            # Log de auditoría
            LogActividad.objects.create(
                ticket=None, usuario=request.user,
                accion=f'Commit revertido: {commit_hash[:7]}',
                detalle=f'Revert ejecutado por: {request.user.get_full_name() or request.user.username}'
            )
            return JsonResponse({
                'success': True,
                'message': f'Commit {commit_hash[:7]} revertido exitosamente. Se creó un nuevo commit de reversión.'
            })
        else:
            # Si hay conflictos, abortar
            subprocess.run(
                ['git', 'revert', '--abort'],
                cwd=str(repo_dir), capture_output=True, text=True, timeout=10
            )
            return JsonResponse({
                'success': False,
                'error': f'No se pudo revertir automáticamente (conflictos). Detalle: {result.stderr[:200]}'
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def health_check(request):
    """Endpoint público para monitoreo del sistema. No requiere autenticación."""
    import django
    from django.db import connection

    # Verificar base de datos
    db_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    # Verificar IA configurada
    from ..ia_engine import GEMINI_API_KEY
    ia_configurada = bool(GEMINI_API_KEY)

    # Contar registros básicos
    total_tickets = Ticket.objects.count()
    total_clientes = Cliente.objects.count()
    total_usuarios = User.objects.count()

    status = 'ok' if db_ok else 'degraded'

    return JsonResponse({
        'status': status,
        'version': '1.0.0',
        'django': django.get_version(),
        'database': 'ok' if db_ok else 'error',
        'ia_engine': 'configured' if ia_configurada else 'not_configured',
        'stats': {
            'tickets': total_tickets,
            'clientes': total_clientes,
            'usuarios': total_usuarios,
        },
    })


