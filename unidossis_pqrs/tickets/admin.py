from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Ticket, ArchivoAdjunto, Cliente, Ciudad, Cargo, MaestroInstitucion, PerfilUsuario,
    ConfiguracionSLA, AlertaSLA, LogActividad, ComentarioTicket, EncuestaSatisfaccion, FeedbackIA,
    SolicitudResetPassword, PermisoRol
)

# Inline para PerfilUsuario dentro de User
class PerfilUsuarioInline(admin.StackedInline):
    model = PerfilUsuario
    can_delete = False
    verbose_name_plural = 'Perfil de Usuario'

class UserAdmin(BaseUserAdmin):
    inlines = (PerfilUsuarioInline,)

# Re-registrar UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('user', 'rol', 'regional', 'cliente')
    list_filter = ('rol', 'regional')
    search_fields = ('user__username', 'user__email')

@admin.register(MaestroInstitucion)
class MaestroInstitucionAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

class ArchivoAdjuntoInline(admin.TabularInline):
    model = ArchivoAdjunto
    extra = 1

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'remitente_email', 'asunto', 'estado', 'fecha_ingreso')
    list_filter = ('estado', 'fecha_ingreso')
    search_fields = ('ticket_id', 'remitente_email', 'asunto')
    readonly_fields = ('ticket_id', 'fecha_ingreso', 'fecha_actualizacion')
    inlines = [ArchivoAdjuntoInline]

@admin.register(ArchivoAdjunto)
class ArchivoAdjuntoAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'archivo', 'subido_por_sistema', 'fecha_subida')

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'user')
    search_fields = ('nombre', 'user__username')

@admin.register(Ciudad)
class CiudadAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(ConfiguracionSLA)
class ConfiguracionSLAAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'dias_alerta_peligro', 'dias_alerta_vencido', 'activo', 'fecha_actualizacion']
    list_editable = ['activo']

@admin.register(AlertaSLA)
class AlertaSLAAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'tipo', 'emails_notificados', 'fecha_envio']
    readonly_fields = ['fecha_envio']

@admin.register(LogActividad)
class LogActividadAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'accion', 'usuario', 'fecha']
    readonly_fields = ['fecha']
    list_filter = ['usuario']

@admin.register(ComentarioTicket)
class ComentarioTicketAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'autor', 'visibilidad', 'fecha']
    list_filter = ['visibilidad']

@admin.register(EncuestaSatisfaccion)
class EncuestaSatisfaccionAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'estado', 'puntuacion', 'fecha_envio', 'fecha_respuesta']
    list_filter = ['estado']
    readonly_fields = ['token', 'fecha_envio']

@admin.register(FeedbackIA)
class FeedbackIAAdmin(admin.ModelAdmin):
    list_display = ['ticket', 'corrector', 'tipificacion_corregida', 'criticidad_corregida', 'fecha']
    readonly_fields = ['fecha']

@admin.register(SolicitudResetPassword)
class SolicitudResetPasswordAdmin(admin.ModelAdmin):
    list_display = ['user', 'email_ingresado', 'estado', 'fecha_solicitud', 'resuelta_por']
    list_filter = ['estado']
    readonly_fields = ['fecha_solicitud']

@admin.register(PermisoRol)
class PermisoRolAdmin(admin.ModelAdmin):
    list_display = ['rol', 'permiso', 'permitido']
    list_filter = ['rol', 'permitido']
    list_editable = ['permitido']

