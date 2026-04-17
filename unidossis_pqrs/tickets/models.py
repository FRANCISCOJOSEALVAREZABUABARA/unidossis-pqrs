from django.db import models
from django.utils.crypto import get_random_string
from django.contrib.auth.models import User
import uuid

def generate_ticket_id():
    return f"PQRS-{get_random_string(6).upper()}"

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('abierto', 'Abierto'),
        ('revision', 'En Revisión'),
        ('resuelto', 'Resuelto'),
        ('cancelado', 'Cancelado / Spam'),
    ]

    REGIONAL_CHOICES = [
        ('liquidos', 'Cundinamarca Líquidos'),
        ('solidos', 'Sólidos'),
        ('marly', 'Marly'),
        ('occidente', 'Regional Occidente'),
        ('antioquia', 'Regional Antioquia'),
        ('costa', 'Regional Costa'),
        ('llanos', 'Regional Llanos'),
        ('eje_cafetero', 'Eje Cafetero'),
    ]

    AREA_CHOICES = [
        ('gerencia', 'Gerencia General'),
        ('produccion', 'Producción y Dirección Técnica'),
        ('comercial', 'Comercial'),
        ('logistica', 'Operaciones y Logística'),
        ('administrativa', 'Administrativa y Financiera'),
        ('talento', 'Talento Humano'),
        ('sst', 'Seguridad y Salud en el Trabajo'),
        ('calidad', 'Aseguramiento de Calidad'),
    ]

    LINEA_CHOICES = [
        ('administrativo', 'Administrativo'),
        ('dosis_anticipada', 'Dosis Anticipada'),
        ('esteriles', 'Esteriles'),
        ('magistral', 'Magistral No Esteriles'),
        ('npt', 'NPT'),
        ('npt_vet', 'NPT Veterinaria'),
        ('oncologia', 'Oncología'),
        ('solidos', 'Solidos'),
        ('todas', 'Todas'),
        ('logistica_linea', 'Logistica'),
        ('logistica_blitz', 'Logistica (Blitz)'),
    ]

    TIPIFICACION_CHOICES = [
        ('producto_no_conforme', 'Producto no conforme'),
        ('no_conformidad_entrega', 'No conformidad entre lo solicitado y entregado'),
        ('farmacovigilancia', 'Reporte de farmacovigilancia'),
        ('diferencia_inventario', 'Diferencia en inventario en custodia'),
        ('entrega_fuera_acuerdo', 'Entrega fuera del acuerdo de servicio'),
        ('error_almacenamiento', 'Error almacenamiento/transporte de medicamentos'),
        ('error_interpretacion', 'Error de interpretación'),
        ('error_embalaje', 'Error de embalaje'),
        ('error_empaque', 'Error de empaque'),
        ('error_re_empaque', 'Error de re empaque'),
        ('error_etiqueta', 'Error en etiqueta/codificado'),
        ('error_despacho', 'Error en despacho'),
        ('incumplimiento', 'Incumplimiento compromisos'),
        ('resultados_micro', 'Solicitud resultados microbiológicos'),
        ('solicitud_cliente', 'Solicitud del cliente'),
    ]

    CRITICIDAD_CHOICES = [
        ('critica', 'Crítica (Riesgo para la vida/salud - Res 0444/1403)'),
        ('mayor', 'Mayor (Afecta calidad/eficacia - Res 0444/1403)'),
        ('menor', 'Menor (Defecto estético/documental)'),
        ('informativa', 'Informativa / Sugerencia'),
    ]

    TIPO_SOLICITUD_CHOICES = [
        ('queja', 'Queja'),
        ('reclamo', 'Reclamo'),
        ('sugerencia', 'Sugerencia'),
        ('pregunta', 'Pregunta'),
        ('felicitacion', 'Felicitación'),
    ]

    ticket_id = models.CharField(max_length=20, unique=True, default=generate_ticket_id, verbose_name="ID del Caso")
    
    # Datos del Solicitante (AC-FR-054-04)
    cliente_rel = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets', verbose_name="Perfil del Cliente")
    entidad_cliente = models.CharField(max_length=200, blank=True, null=True, verbose_name="Entidad / Cliente")
    institucion = models.CharField(max_length=200, blank=True, null=True, verbose_name="Institución")
    ciudad = models.CharField(max_length=150, blank=True, null=True, verbose_name="Ciudad")
    remitente_nombre = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nombre del Solicitante")
    solicitante_cargo = models.CharField(max_length=150, blank=True, null=True, verbose_name="Cargo del Solicitante")
    telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name="Teléfono")
    remitente_email = models.EmailField(verbose_name="Correo Electrónico")

    # Tipo y Contenido
    tipo_solicitud = models.CharField(max_length=20, choices=TIPO_SOLICITUD_CHOICES, default='queja', verbose_name="Tipo de Solicitud")
    asunto = models.CharField(max_length=300, verbose_name="Asunto")
    cuerpo = models.TextField(verbose_name="Cuerpo del mensaje")
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES, default='abierto', verbose_name="Estado")
    regional = models.CharField(max_length=50, choices=REGIONAL_CHOICES, blank=True, null=True, verbose_name="Regional Asignada")
    proceso = models.CharField(max_length=50, choices=AREA_CHOICES, blank=True, null=True, verbose_name="Área / Proceso")
    linea_servicio = models.CharField(max_length=50, choices=LINEA_CHOICES, blank=True, null=True, verbose_name="Línea")
    tipificacion = models.CharField(max_length=100, choices=TIPIFICACION_CHOICES, blank=True, null=True, verbose_name="Tipificación")
    criticidad = models.CharField(max_length=20, choices=CRITICIDAD_CHOICES, blank=True, null=True, verbose_name="Nivel de Criticidad")
    responsable = models.CharField(max_length=150, blank=True, null=True, verbose_name="Responsable Asignado")
    respuesta_oficial = models.TextField(blank=True, null=True, verbose_name="Respuesta de Unidossis")
    
    # Inteligencia Artificial
    analisis_ia = models.TextField(blank=True, null=True, verbose_name="Análisis de IA")
    resumen_cliente_ia = models.CharField(max_length=400, blank=True, null=True, verbose_name="Resumen IA para Cliente")
    clasificado_por_ia = models.BooleanField(default=False, verbose_name="Auto-Clasificado por IA")
    
    # Notificaciones por SMTP
    auto_respuesta_enviada = models.BooleanField(default=False, verbose_name="Acuse de recibo enviado al cliente")
    respuesta_formal_enviada = models.BooleanField(default=False, verbose_name="Notificación de Cierre enviada al cliente")
    
    fecha_ingreso = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Ingreso")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Última actualización")

    def __str__(self):
        return f"{self.ticket_id} - {self.asunto}"
        
    def dias_transcurridos(self):
        from django.utils import timezone
        diff = timezone.now() - self.fecha_ingreso
        return diff.days

    def estado_sla(self):
        if self.estado in ['resuelto', 'cancelado']:
            return 'cerrado'
        dias = self.dias_transcurridos()
        if dias <= 10:
            return 'bien' # < 11 días
        elif dias <= 14:
            return 'peligro' # 11-14 días
        else:
            return 'vencido' # >= 15 días
    
    class Meta:
        verbose_name = "Ticket PQRS"
        verbose_name_plural = "Tickets PQRS"
        ordering = ['-fecha_ingreso']

class ArchivoAdjunto(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='archivos_adjuntos')
    archivo = models.FileField(upload_to='adjuntos_pqrs/', verbose_name="Archivo Adjunto")
    subido_por_sistema = models.BooleanField(default=False, verbose_name="¿Descargado del correo?")
    es_respuesta_agente = models.BooleanField(default=False, verbose_name="Adjuntado por Unidossis en la Respuesta")
    es_soporte_interno = models.BooleanField(default=False, verbose_name="Soporte/Evidencia Interna de Gestión")
    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Adjunto para {self.ticket.ticket_id}"

    class Meta:
        verbose_name = "Archivo Adjunto"
        verbose_name_plural = "Archivos Adjuntos"

class Cliente(models.Model):
    REGIONAL_CHOICES = [
        ('liquidos', 'Cundinamarca Líquidos'),
        ('solidos', 'Sólidos'),
        ('marly', 'Marly'),
        ('occidente', 'Regional Occidente'),
        ('antioquia', 'Regional Antioquia'),
        ('costa', 'Regional Costa'),
        ('llanos', 'Regional Llanos'),
        ('eje_cafetero', 'Eje Cafetero'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='cliente_perfil', verbose_name="Usuario Asociado")
    nombre = models.CharField(max_length=255, unique=True, verbose_name="Nombre del Cliente")
    ciudad = models.ForeignKey('Ciudad', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ciudad/Municipio")
    regional = models.CharField(max_length=50, choices=REGIONAL_CHOICES, null=True, blank=True, verbose_name="Regional que lo atiende")
    email_principal = models.EmailField(max_length=255, null=True, blank=True, verbose_name="Correo Principal (Obligatorio)")
    emails_adicionales = models.TextField(blank=True, null=True, verbose_name="Correos Adicionales (Separados por coma)")
    activo = models.BooleanField(default=True, verbose_name="Cliente Activo")
    
    def __str__(self):
        return f"{self.nombre} (@{self.user.username})" if self.user else self.nombre
    
    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']

class Ciudad(models.Model):
    nombre = models.CharField(max_length=150, unique=True, verbose_name="Nombre de la Ciudad/Municipio")
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Ciudad"
        verbose_name_plural = "Ciudades"
        ordering = ['nombre']

class Cargo(models.Model):
    nombre = models.CharField(max_length=150, unique=True, verbose_name="Nombre del Cargo")
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        ordering = ['nombre']

class MaestroInstitucion(models.Model):
    nombre = models.CharField(max_length=255, unique=True, verbose_name="Nombre de Referencia")
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name = "Maestro de Institución"
        verbose_name_plural = "Maestro de Instituciones"
        ordering = ['nombre']

class PerfilUsuario(models.Model):
    ROL_CHOICES = [
        ('superadmin', 'Super Administrador'),
        ('admin_pqrs', 'Administrador PQRS'),
        ('director_regional', 'Director Regional'),
        ('agente', 'Agente / Consultor'),
        ('cliente', 'Cliente Institución'),
    ]

    REGIONAL_CHOICES = [
        ('liquidos', 'Cundinamarca Líquidos'),
        ('solidos', 'Sólidos'),
        ('marly', 'Marly'),
        ('occidente', 'Regional Occidente'),
        ('antioquia', 'Regional Antioquia'),
        ('costa', 'Regional Costa'),
        ('llanos', 'Regional Llanos'),
        ('eje_cafetero', 'Eje Cafetero'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=30, choices=ROL_CHOICES, default='admin_pqrs')
    regional = models.CharField(max_length=50, choices=REGIONAL_CHOICES, blank=True, null=True, help_text="Solo para Directores Regionales y Agentes regionales")
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name="Teléfono / Celular")
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, help_text="Solo para usuarios de tipo Cliente")
    debe_cambiar_password = models.BooleanField(default=False, verbose_name="Debe cambiar contraseña",
        help_text="Si está activo, se forzará al usuario a cambiar su contraseña en el próximo login")

    def __str__(self):
        return f"{self.user.username} - {self.get_rol_display()}"

    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"


# ─────────────────────────────────────────────────────────────
# MÓDULO CRM: SLA, ALERTAS, COMENTARIOS, CSAT, IA FEEDBACK
# ─────────────────────────────────────────────────────────────

class ConfiguracionSLA(models.Model):
    """Permite parametrizar los días límite del SLA y a quién alertar."""
    nombre = models.CharField(max_length=100, default="Configuración SLA Principal", verbose_name="Nombre de la Configuración")
    dias_alerta_peligro = models.IntegerField(default=11, verbose_name="Días para alerta 'En Peligro'")
    dias_alerta_vencido = models.IntegerField(default=15, verbose_name="Días para alerta 'Vencido / Escalamiento'")
    # Emails de los responsables de recibir alertas
    emails_alerta_peligro = models.TextField(
        blank=True, default='',
        verbose_name="Emails para alertas de 'En Peligro'",
        help_text="Separados por coma. Ej: regional@unidossis.com, supervisor@unidossis.com"
    )
    emails_alerta_vencido = models.TextField(
        blank=True, default='',
        verbose_name="Emails para alertas de 'Vencido'",
        help_text="Separados por coma. Ej: admin@unidossis.com, calidad@unidossis.com"
    )
    # Notificación por celular (WhatsApp/SMS - campo para configuración futura)
    celulares_alerta = models.TextField(
        blank=True, default='',
        verbose_name="Celulares para alertas (WhatsApp/SMS)",
        help_text="Solo dígitos, separados por coma. Ej: 3001234567,3109876543"
    )
    activo = models.BooleanField(default=True, verbose_name="Configuración activa")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def get_emails_peligro(self):
        return [e.strip() for e in self.emails_alerta_peligro.split(',') if e.strip()]

    def get_emails_vencido(self):
        return [e.strip() for e in self.emails_alerta_vencido.split(',') if e.strip()]

    def get_celulares(self):
        return [c.strip() for c in self.celulares_alerta.split(',') if c.strip()]

    def __str__(self):
        return f"{self.nombre} (Peligro: {self.dias_alerta_peligro}d | Vencido: {self.dias_alerta_vencido}d)"

    class Meta:
        verbose_name = "Configuración SLA"
        verbose_name_plural = "Configuraciones SLA"


class AlertaSLA(models.Model):
    """Registro de alertas SLA enviadas — evita envíos duplicados."""
    TIPO_CHOICES = [
        ('peligro', 'Alerta de Peligro (próximo a vencer)'),
        ('vencido', 'Alerta de Vencimiento / Escalamiento'),
    ]
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='alertas_sla')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    emails_notificados = models.TextField(blank=True)
    fecha_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Alerta SLA"
        verbose_name_plural = "Alertas SLA"
        unique_together = ('ticket', 'tipo')  # No enviar la misma alerta dos veces por ticket

    def __str__(self):
        return f"Alerta {self.tipo} — {self.ticket.ticket_id}"


class LogActividad(models.Model):
    """Registro de auditoría de todas las acciones sobre un ticket o del sistema."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    accion = models.CharField(max_length=300, verbose_name="Acción realizada")
    detalle = models.TextField(blank=True, null=True, verbose_name="Detalle adicional")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de Actividad"
        verbose_name_plural = "Logs de Actividad"
        ordering = ['-fecha']

    def __str__(self):
        prefix = f"[{self.ticket.ticket_id}]" if self.ticket else "[Sistema]"
        return f"{prefix} {self.accion}"


class ComentarioTicket(models.Model):
    """Hilo de comunicación interna o pública por ticket (tipo CRM)."""
    VISIBILIDAD_CHOICES = [
        ('interno', 'Solo equipo interno Unidossis'),
        ('publico', 'Visible para el cliente'),
    ]
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    texto = models.TextField(verbose_name="Comentario")
    visibilidad = models.CharField(max_length=10, choices=VISIBILIDAD_CHOICES, default='interno')
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comentario de Ticket"
        verbose_name_plural = "Comentarios de Tickets"
        ordering = ['fecha']

    def __str__(self):
        return f"Comentario en {self.ticket.ticket_id} por {self.autor}"


class EncuestaSatisfaccion(models.Model):
    """Encuesta CSAT enviada al cliente al cerrar un ticket.
    La respuesta puede confirmar el cierre o reabrir el ticket.
    """
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente de respuesta'),
        ('satisfecho', 'Cliente satisfecho — ticket cerrado'),
        ('insatisfecho', 'Cliente insatisfecho — ticket reabierto'),
        ('expirada', 'Encuesta expirada sin respuesta'),
    ]
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name='encuesta_csat')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    puntuacion = models.IntegerField(null=True, blank=True, verbose_name="Puntuación (1-5 estrellas)")
    comentario_cliente = models.TextField(blank=True, null=True, verbose_name="Comentario del cliente")
    fecha_envio = models.DateTimeField(auto_now_add=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Encuesta de Satisfacción (CSAT)"
        verbose_name_plural = "Encuestas de Satisfacción (CSAT)"

    def __str__(self):
        return f"CSAT {self.ticket.ticket_id} — {self.get_estado_display()}"


class FeedbackIA(models.Model):
    """Registro de correcciones manuales al análisis de IA — base para aprendizaje continuo."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='feedbacks_ia')
    corrector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    # Clasificación original de la IA
    ia_linea_original = models.CharField(max_length=50, blank=True)
    ia_proceso_original = models.CharField(max_length=50, blank=True)
    ia_tipificacion_original = models.CharField(max_length=100, blank=True)
    ia_criticidad_original = models.CharField(max_length=20, blank=True)
    # Clasificación correcta según el agente
    linea_corregida = models.CharField(max_length=50, blank=True)
    proceso_corregido = models.CharField(max_length=50, blank=True)
    tipificacion_corregida = models.CharField(max_length=100, blank=True)
    criticidad_corregida = models.CharField(max_length=20, blank=True)
    observacion = models.TextField(blank=True, null=True, verbose_name="Razón de la corrección")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Feedback de IA"
        verbose_name_plural = "Feedbacks de IA"
        ordering = ['-fecha']

    def __str__(self):
        return f"Feedback IA: {self.ticket.ticket_id} ({self.fecha.strftime('%d/%m/%Y')})"


class IntentoLogin(models.Model):
    """Registra intentos de login para rate limiting y auditoría."""
    ip = models.GenericIPAddressField(verbose_name="Dirección IP")
    username = models.CharField(max_length=150, verbose_name="Usuario intentado")
    exitoso = models.BooleanField(default=False)
    user_agent = models.TextField(blank=True, default='', verbose_name="Navegador")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Intento de Login"
        verbose_name_plural = "Intentos de Login"
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['ip', 'fecha']),
            models.Index(fields=['username', 'fecha']),
        ]

    def __str__(self):
        estado = "✅" if self.exitoso else "❌"
        return f"{estado} {self.username} desde {self.ip} ({self.fecha.strftime('%d/%m/%Y %H:%M')})"
