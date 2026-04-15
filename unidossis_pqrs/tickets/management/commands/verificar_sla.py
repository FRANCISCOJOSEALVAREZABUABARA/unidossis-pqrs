"""
Comando: python manage.py verificar_sla

Verifica el estado SLA de todos los tickets abiertos y envía alertas
al correo según los usuarios internos registrados en el sistema.

Lógica de notificación:
  - Alerta "En Peligro": notifica al Director Regional del ticket + Supervisores
  - Alerta "Vencido":    notifica a los Administradores PQRS + Super Administradores

Ejecutar programáticamente con Windows Task Scheduler o cron.
Ejemplo Windows Task Scheduler: cada día a las 8am:
  python manage.py verificar_sla
"""

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from tickets.models import Ticket, AlertaSLA, LogActividad, ConfiguracionSLA, PerfilUsuario


EMAIL_ORIGEN = 'UNIDOSSIS PQRS - Alertas SLA <alertas@unidossis.com.co>'


class Command(BaseCommand):
    help = 'Verifica el SLA de tickets abiertos y envía alertas a los usuarios internos registrados'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            f'\n[{timezone.now().strftime("%d/%m/%Y %H:%M")}] Iniciando verificacion SLA UNIDOSSIS PQRS\n'
        ))

        # 1. Obtener configuración SLA activa (o usar defaults)
        config = ConfiguracionSLA.objects.filter(activo=True).first()
        if not config:
            config = ConfiguracionSLA(
                dias_alerta_peligro=11,
                dias_alerta_vencido=15,
            )
            self.stdout.write(self.style.WARNING(
                '  No hay configuracion SLA activa. Usando valores por defecto (peligro: 11d, vencido: 15d).'
            ))

        # 2. Precargar los destinatarios desde usuarios internos
        directores = {
            p.regional: p.user.email
            for p in PerfilUsuario.objects.filter(rol='director_regional').select_related('user')
            if p.regional and p.user.email
        }
        supervisores_emails = list(
            PerfilUsuario.objects.filter(rol='supervisor', user__is_active=True)
            .select_related('user')
            .exclude(user__email='')
            .values_list('user__email', flat=True)
        )
        admins_emails = list(
            PerfilUsuario.objects.filter(rol__in=['admin_pqrs', 'superadmin'], user__is_active=True)
            .select_related('user')
            .exclude(user__email='')
            .values_list('user__email', flat=True)
        )

        self.stdout.write(f'  Directores Regionales con email: {len(directores)}')
        self.stdout.write(f'  Supervisores con email: {len(supervisores_emails)}')
        self.stdout.write(f'  Admins/Superadmins con email: {len(admins_emails)}\n')

        # 3. Tickets abiertos (excluye resueltos y cancelados)
        tickets_abiertos = Ticket.objects.exclude(estado__in=['resuelto', 'cancelado'])
        peligro_count = 0
        vencido_count = 0

        for ticket in tickets_abiertos:
            dias = ticket.dias_transcurridos()
            sla = ticket.estado_sla()

            if sla == 'peligro' and dias >= config.dias_alerta_peligro:
                # Destinatarios: Director de la regional del ticket + supervisores
                destinatarios = list(supervisores_emails)  # copia
                if ticket.regional and ticket.regional in directores:
                    destinatarios.insert(0, directores[ticket.regional])
                # Eliminar duplicados
                destinatarios = list(dict.fromkeys(destinatarios))
                self._enviar_alerta(ticket, 'peligro', destinatarios, dias, config)
                peligro_count += 1

            elif sla == 'vencido' and dias >= config.dias_alerta_vencido:
                # Destinatarios: Admins PQRS + Superadmins
                destinatarios = list(dict.fromkeys(admins_emails))
                self._enviar_alerta(ticket, 'vencido', destinatarios, dias, config)
                vencido_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Verificacion completada:\n'
            f'   -> Alertas de peligro enviadas: {peligro_count}\n'
            f'   -> Alertas de vencimiento (escalamiento) enviadas: {vencido_count}\n'
        ))

    def _enviar_alerta(self, ticket, tipo, destinatarios, dias, config):
        """Envía la alerta de SLA por email. Evita duplicados vía AlertaSLA."""
        # Verificar si ya se envió esta alerta para este ticket
        ya_enviada = AlertaSLA.objects.filter(ticket=ticket, tipo=tipo).exists()
        if ya_enviada:
            return  # No reenviar

        if tipo == 'peligro':
            asunto = f'ALERTA SLA PELIGRO - Ticket {ticket.ticket_id} lleva {dias} dias sin resolver'
            cuerpo = (
                f'Estimado equipo UNIDOSSIS,\n\n'
                f'El siguiente ticket PQRS esta POR VENCER su SLA:\n\n'
                f'  - ID del Caso: {ticket.ticket_id}\n'
                f'  - Asunto: {ticket.asunto}\n'
                f'  - Cliente: {ticket.remitente_nombre or "No especificado"}\n'
                f'  - Regional: {ticket.get_regional_display() if ticket.regional else "Sin asignar"}\n'
                f'  - Dias transcurridos: {dias} dias\n'
                f'  - Responsable: {ticket.responsable or "Sin asignar"}\n'
                f'  - Estado actual: {ticket.get_estado_display()}\n\n'
                f'Por favor atienda este caso a la brevedad para evitar el incumplimiento del acuerdo de servicio.\n\n'
                f'-- UNIDOSSIS PQRS - Sistema Automatico de Alertas'
            )
        else:  # vencido
            asunto = f'ESCALAMIENTO SLA VENCIDO - Ticket {ticket.ticket_id} lleva {dias} dias VENCIDO'
            cuerpo = (
                f'Estimada Administracion UNIDOSSIS,\n\n'
                f'El siguiente ticket PQRS ha SUPERADO el tiempo maximo de SLA y requiere escalamiento inmediato:\n\n'
                f'  - ID del Caso: {ticket.ticket_id}\n'
                f'  - Asunto: {ticket.asunto}\n'
                f'  - Cliente/Institucion: {ticket.remitente_nombre or "No especificado"} / {ticket.entidad_cliente or ""}\n'
                f'  - Regional: {ticket.get_regional_display() if ticket.regional else "Sin asignar"}\n'
                f'  - Dias vencido: {dias} dias (limite: {config.dias_alerta_vencido} dias)\n'
                f'  - Responsable actual: {ticket.responsable or "Sin asignar"}\n'
                f'  - Estado actual: {ticket.get_estado_display()}\n\n'
                f'ACCION REQUERIDA: Este caso debe reasignarse o escalarse de forma inmediata.\n\n'
                f'-- UNIDOSSIS PQRS - Sistema Automatico de Escalamiento'
            )

        # Enviar correo si hay destinatarios
        if destinatarios:
            try:
                send_mail(
                    subject=asunto,
                    message=cuerpo,
                    from_email=EMAIL_ORIGEN,
                    recipient_list=destinatarios,
                    fail_silently=False,
                )
                # Registrar la alerta para no duplicarla
                AlertaSLA.objects.create(
                    ticket=ticket,
                    tipo=tipo,
                    emails_notificados=', '.join(destinatarios)
                )
                # Registrar en log de actividad
                LogActividad.objects.create(
                    ticket=ticket,
                    usuario=None,
                    accion=f'Alerta SLA automatica enviada ({tipo}): {dias} dias transcurridos',
                    detalle=f'Notificados: {", ".join(destinatarios)}'
                )
                self.stdout.write(
                    f'  [{tipo.upper()}] {ticket.ticket_id} -- {dias}d -- Notificados: {", ".join(destinatarios)}'
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  Error enviando alerta para {ticket.ticket_id}: {str(e)}'
                ))
        else:
            self.stdout.write(self.style.WARNING(
                f'  [{tipo.upper()}] {ticket.ticket_id} -- Sin destinatarios con email configurado para esta alerta.'
            ))
