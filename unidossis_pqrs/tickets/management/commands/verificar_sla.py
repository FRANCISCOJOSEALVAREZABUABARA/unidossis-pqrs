"""
Comando: python manage.py verificar_sla

Verifica el estado SLA de todos los tickets abiertos y envía alertas
al correo según la configuración activa de ConfiguracionSLA.

LÓGICA DE DESTINATARIOS (prioridad en cascada):
  Alerta PELIGRO:
    1. Emails configurados en ConfiguracionSLA.emails_alerta_peligro
    2. Director Regional de la regional del ticket
    3. Supervisores activos con email

  Alerta VENCIDO:
    1. Emails configurados en ConfiguracionSLA.emails_alerta_vencido
    2. Admins PQRS + Superadmins activos con email

ANTI-DUPLICADO:
  - No reenvía la misma alerta (tipo) si ya existe en AlertaSLA para el ticket
  - Pasados 'dias_reenvio' días desde la última alerta, permite reenviar (re-escalamiento)

OPCIONES:
  --dry-run     Simula sin enviar emails ni crear registros
  --resumen     Muestra tabla de todos los tickets con estado SLA
  --forzar      Ignora el anti-duplicado (útil para re-notificar manualmente)
  --solo-tipo   peligro | vencido  (filtra solo ese tipo de alerta)

EJEMPLOS:
  python manage.py verificar_sla                        # Ejecución normal
  python manage.py verificar_sla --dry-run              # Simulación segura
  python manage.py verificar_sla --resumen              # Solo reporte, sin emails
  python manage.py verificar_sla --solo-tipo=vencido    # Solo escalamientos

PROGRAMACIÓN EN PYTHONANYWHERE:
  Dashboard → Tasks → Crear tarea programada diaria:
  /home/unidossis/.virtualenvs/venv/bin/python /home/unidossis/unidossis_pqrs/manage.py verificar_sla
  Hora recomendada: 08:00 AM (hora Colombia UTC-5)
"""

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from django.template.loader import render_to_string

from tickets.models import (
    Ticket, AlertaSLA, LogActividad, ConfiguracionSLA, PerfilUsuario
)

EMAIL_ORIGEN = 'UNIDOSSIS PQRS - Alertas SLA <alertas@unidossis.com.co>'
DIAS_REENVIO_DEFAULT = 7  # Después de N días puede reenviar la misma alerta


class Command(BaseCommand):
    help = 'Verifica el SLA de tickets abiertos y envía alertas. Soporte --dry-run y --resumen.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Simula la ejecución sin enviar emails ni crear registros en DB.',
        )
        parser.add_argument(
            '--resumen',
            action='store_true',
            default=False,
            help='Muestra un resumen del estado SLA de todos los tickets abiertos (sin enviar alertas).',
        )
        parser.add_argument(
            '--forzar',
            action='store_true',
            default=False,
            help='Ignora el control anti-duplicado y reenvía todas las alertas.',
        )
        parser.add_argument(
            '--solo-tipo',
            type=str,
            choices=['peligro', 'vencido'],
            default=None,
            help='Procesa únicamente alertas de ese tipo.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        solo_resumen = options['resumen']
        forzar = options['forzar']
        solo_tipo = options['solo_tipo']

        ahora = timezone.now()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'╔══════════════════════════════════════════════════╗'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'║  UNIDOSSIS PQRS — Verificación SLA Automática   ║'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'║  {ahora.strftime("%d/%m/%Y %H:%M")} (UTC{timezone.get_current_timezone_name()[:6]})              ║'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'╚══════════════════════════════════════════════════╝'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('  ⚠  MODO DRY-RUN: No se enviarán emails ni se escribirá en DB.\n'))

        # ── 1. Configuración SLA ─────────────────────────────────────────────
        config = ConfiguracionSLA.objects.filter(activo=True).first()
        if not config:
            config = ConfiguracionSLA(
                dias_alerta_peligro=11,
                dias_alerta_vencido=15,
                emails_alerta_peligro='',
                emails_alerta_vencido='',
            )
            self.stdout.write(self.style.WARNING(
                '  ⚠  Sin ConfiguracionSLA activa. Usando defaults: peligro=11d, vencido=15d\n'
            ))
        else:
            self.stdout.write(
                f'  Config SLA: "{config.nombre}" | Peligro={config.dias_alerta_peligro}d | '
                f'Vencido={config.dias_alerta_vencido}d\n'
            )

        # ── 2. Precargar destinatarios desde perfiles de usuario ─────────────
        directores = {
            p.regional: p.user.email
            for p in PerfilUsuario.objects.filter(
                rol='director_regional', user__is_active=True
            ).select_related('user')
            if p.regional and p.user.email
        }
        supervisores_emails = list(
            PerfilUsuario.objects.filter(rol='supervisor', user__is_active=True)
            .exclude(user__email='').values_list('user__email', flat=True)
        )
        admins_emails = list(
            PerfilUsuario.objects.filter(
                rol__in=['admin_pqrs', 'superadmin'], user__is_active=True
            ).exclude(user__email='').values_list('user__email', flat=True)
        )

        self.stdout.write(f'  Directores Regionales con email : {len(directores)}')
        self.stdout.write(f'  Supervisores con email          : {len(supervisores_emails)}')
        self.stdout.write(f'  Admins/Superadmins con email    : {len(admins_emails)}')
        self.stdout.write('')

        # ── 3. Tickets abiertos ──────────────────────────────────────────────
        tickets_abiertos = list(
            Ticket.objects.exclude(estado__in=['resuelto', 'cancelado'])
            .select_related('cliente_rel')
            .prefetch_related('alertas_sla')
            .order_by('fecha_ingreso')
        )

        self.stdout.write(f'  Tickets abiertos a verificar: {len(tickets_abiertos)}\n')

        # ── 4. Resumen opcional ──────────────────────────────────────────────
        if solo_resumen:
            self._mostrar_resumen(tickets_abiertos, config)
            return

        # ── 5. Procesar alertas ──────────────────────────────────────────────
        stats = {
            'bien': 0, 'peligro_enviado': 0, 'peligro_saltado': 0,
            'vencido_enviado': 0, 'vencido_saltado': 0, 'sin_destinatarios': 0,
            'errores': 0,
        }

        for ticket in tickets_abiertos:
            dias = ticket.dias_transcurridos()
            sla = ticket.estado_sla()

            if sla == 'bien':
                stats['bien'] += 1
                continue

            if sla == 'peligro' and solo_tipo in (None, 'peligro'):
                ok = self._procesar_alerta(
                    ticket, 'peligro', dias, config, directores, supervisores_emails,
                    admins_emails, dry_run, forzar, stats, ahora
                )
            elif sla == 'vencido' and solo_tipo in (None, 'vencido'):
                ok = self._procesar_alerta(
                    ticket, 'vencido', dias, config, directores, supervisores_emails,
                    admins_emails, dry_run, forzar, stats, ahora
                )

        # ── 6. Resumen final ─────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 52))
        self.stdout.write(self.style.SUCCESS('  RESUMEN FINAL'))
        self.stdout.write(self.style.SUCCESS('═' * 52))
        self.stdout.write(f'  Tickets en BIEN            : {stats["bien"]}')
        self.stdout.write(
            self.style.WARNING(f'  Alertas PELIGRO enviadas   : {stats["peligro_enviado"]}')
        )
        self.stdout.write(f'  Alertas peligro saltadas   : {stats["peligro_saltado"]} (ya notificados)')
        self.stdout.write(
            self.style.ERROR(f'  Escalamientos VENCIDO      : {stats["vencido_enviado"]}')
        )
        self.stdout.write(f'  Escalamientos saltados     : {stats["vencido_saltado"]} (ya notificados)')
        self.stdout.write(
            self.style.WARNING(f'  Sin destinatarios          : {stats["sin_destinatarios"]}')
        )
        if stats['errores']:
            self.stdout.write(self.style.ERROR(f'  Errores de envío           : {stats["errores"]}'))
        self.stdout.write(self.style.SUCCESS('═' * 52))
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING('  Ejecución en modo DRY-RUN: ningún email fue enviado.'))

    def _procesar_alerta(
        self, ticket, tipo, dias, config, directores,
        supervisores_emails, admins_emails, dry_run, forzar, stats, ahora
    ):
        """Decide si enviar la alerta y la envía si corresponde."""
        base_url = 'https://pqrs.unidossis.com.co'

        # Anti-duplicado: verificar si ya fue notificado
        if not forzar:
            alerta_existente = AlertaSLA.objects.filter(ticket=ticket, tipo=tipo).first()
            if alerta_existente:
                dias_desde_ultima = (ahora - alerta_existente.fecha_envio).days
                if dias_desde_ultima < DIAS_REENVIO_DEFAULT:
                    stats[f'{tipo}_saltado'] += 1
                    return False  # Ya notificado recientemente

        # Construir lista de destinatarios
        destinatarios = []

        if tipo == 'peligro':
            # Prioridad 1: emails configurados en el SLA
            destinatarios += config.get_emails_peligro()
            # Prioridad 2: director de la regional del ticket
            if ticket.regional and ticket.regional in directores:
                email_director = directores[ticket.regional]
                if email_director not in destinatarios:
                    destinatarios.append(email_director)
            # Prioridad 3: supervisores
            for e in supervisores_emails:
                if e not in destinatarios:
                    destinatarios.append(e)
            limite_dias = config.dias_alerta_peligro
        else:  # vencido
            # Prioridad 1: emails configurados en el SLA
            destinatarios += config.get_emails_vencido()
            # Prioridad 2: admins y superadmins
            for e in admins_emails:
                if e not in destinatarios:
                    destinatarios.append(e)
            limite_dias = config.dias_alerta_vencido

        if not destinatarios:
            stats['sin_destinatarios'] += 1
            self.stdout.write(self.style.WARNING(
                f'  [{tipo.upper()}] {ticket.ticket_id} | {dias}d | Sin destinatarios configurados'
            ))
            return False

        # Preparar contexto del email
        dias_excedido = max(0, dias - limite_dias)
        url_ticket = f'{base_url}/ticket/{ticket.ticket_id}/'
        cliente_nombre = (
            ticket.remitente_nombre or
            (ticket.cliente_rel.nombre if ticket.cliente_rel else None) or
            ticket.entidad_cliente or
            'No especificado'
        )
        ctx = {
            'tipo': tipo,
            'ticket_id': ticket.ticket_id,
            'asunto': ticket.asunto or '(Sin asunto)',
            'cliente': cliente_nombre,
            'regional': ticket.get_regional_display() if ticket.regional else 'Sin asignar',
            'responsable': ticket.responsable or 'Sin asignar',
            'estado': ticket.get_estado_display(),
            'dias': dias,
            'dias_excedido': dias_excedido,
            'limite_dias': limite_dias,
            'fecha_ingreso': ticket.fecha_ingreso.strftime('%d/%m/%Y %H:%M'),
            'fecha_generacion': ahora.strftime('%d/%m/%Y %H:%M'),
            'url_ticket': url_ticket,
        }

        # Construir subjects
        if tipo == 'peligro':
            subject = f'[PELIGRO SLA] Ticket {ticket.ticket_id} lleva {dias} días — Unidossis PQRS'
        else:
            subject = f'[ESCALAMIENTO SLA] Ticket {ticket.ticket_id} VENCIDO {dias_excedido}d — Acción Inmediata'

        # Texto plano (fallback)
        plain_lines = [
            f'{"ALERTA SLA — PELIGRO" if tipo == "peligro" else "ESCALAMIENTO SLA — VENCIDO"}',
            '',
            f'Ticket    : {ticket.ticket_id}',
            f'Asunto    : {ctx["asunto"]}',
            f'Cliente   : {ctx["cliente"]}',
            f'Regional  : {ctx["regional"]}',
            f'Responsable: {ctx["responsable"]}',
            f'Días      : {dias} días',
            f'Límite    : {limite_dias} días',
            f'',
            f'URL: {url_ticket}',
            '',
            '— UNIDOSSIS PQRS Sistema Automático de Alertas',
        ]
        plain_text = '\n'.join(plain_lines)

        # Renderizar HTML
        html_message = None
        try:
            html_message = render_to_string('tickets/emails/alerta_sla.html', ctx)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'    Template HTML no disponible: {e}'))

        if dry_run:
            self.stdout.write(
                f'  [DRY-RUN/{tipo.upper()}] {ticket.ticket_id} | {dias}d | '
                f'→ {len(destinatarios)} destinatarios: {", ".join(destinatarios)}'
            )
            stats[f'{tipo}_enviado'] += 1
            return True

        # Enviar
        try:
            send_mail(
                subject=subject,
                message=plain_text,
                from_email=EMAIL_ORIGEN,
                recipient_list=destinatarios,
                html_message=html_message,
                fail_silently=False,
            )

            # Registrar alerta (eliminar previa si existe, para permitir reenvíos)
            AlertaSLA.objects.filter(ticket=ticket, tipo=tipo).delete()
            AlertaSLA.objects.create(
                ticket=ticket,
                tipo=tipo,
                emails_notificados=', '.join(destinatarios)
            )

            LogActividad.objects.create(
                ticket=ticket,
                usuario=None,
                accion=f'Alerta SLA automática enviada ({tipo}): {dias}d transcurridos',
                detalle=f'Notificados ({len(destinatarios)}): {", ".join(destinatarios)}'
            )

            self.stdout.write(
                f'  [{"⚠ PELIGRO" if tipo == "peligro" else "🚨 VENCIDO"}] '
                f'{ticket.ticket_id} | {dias}d | '
                f'✓ Enviado a {len(destinatarios)} destinatarios'
            )
            stats[f'{tipo}_enviado'] += 1
            return True

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'  [ERROR] {ticket.ticket_id} | {tipo} | {str(e)}'
            ))
            stats['errores'] += 1
            return False

    def _mostrar_resumen(self, tickets, config):
        """Muestra tabla de estado SLA de todos los tickets abiertos."""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('  RESUMEN DE ESTADO SLA — TICKETS ABIERTOS'))
        self.stdout.write('  ' + '─' * 80)
        self.stdout.write(
            f'  {"ID":<18} {"Días":>5} {"SLA":<10} {"Regional":<18} {"Responsable":<20}'
        )
        self.stdout.write('  ' + '─' * 80)

        conteo = {'bien': 0, 'peligro': 0, 'vencido': 0}

        for t in tickets:
            dias = t.dias_transcurridos()
            sla = t.estado_sla()
            conteo[sla] = conteo.get(sla, 0) + 1
            regional = t.get_regional_display()[:16] if t.regional else 'Sin regional'
            responsable = (t.responsable or 'Sin asignar')[:18]

            if sla == 'vencido':
                linea = self.style.ERROR(
                    f'  {t.ticket_id:<18} {dias:>5} VENCIDO    {regional:<18} {responsable}'
                )
            elif sla == 'peligro':
                linea = self.style.WARNING(
                    f'  {t.ticket_id:<18} {dias:>5} PELIGRO    {regional:<18} {responsable}'
                )
            else:
                linea = f'  {t.ticket_id:<18} {dias:>5} bien       {regional:<18} {responsable}'
            self.stdout.write(linea)

        self.stdout.write('  ' + '─' * 80)
        self.stdout.write(
            f'  Total: {len(tickets)} abiertos | '
            f'Bien: {conteo.get("bien",0)} | '
            f'Peligro: {conteo.get("peligro",0)} | '
            f'Vencido: {conteo.get("vencido",0)}'
        )
        self.stdout.write(
            f'  SLA Config: Peligro={config.dias_alerta_peligro}d | '
            f'Vencido={config.dias_alerta_vencido}d'
        )
        self.stdout.write('')
