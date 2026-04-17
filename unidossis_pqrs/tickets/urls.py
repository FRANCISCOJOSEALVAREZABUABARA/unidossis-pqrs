from django.urls import path
from . import views

urlpatterns = [
    # ─── Autenticación ───────────────────────────────────────
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('acceso-denegado/', views.acceso_denegado_view, name='acceso_denegado'),
    path('cambiar-password/', views.cambiar_password_view, name='cambiar_password'),

    # ─── Dashboard y Tickets ─────────────────────────────────
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/crear-pqrs/', views.crear_pqrs_manual_view, name='crear_pqrs_manual'),
    path('ticket/<str:ticket_id>/', views.ticket_detail_view, name='ticket_detail'),

    # ─── Gestión de Clientes ─────────────────────────────────
    path('gestionar-clientes/', views.gestionar_clientes_view, name='gestionar_clientes'),

    # ─── Portal del Cliente ──────────────────────────────────
    path('portal/', views.public_pqrs_view, name='public_portal'),
    path('cliente/dashboard/', views.portal_cliente_dashboard, name='portal_cliente_dashboard'),
    path('cliente/analiticas/', views.portal_cliente_analytics, name='portal_cliente_analytics'),

    # ─── Configuración SLA ───────────────────────────────────
    path('configurar-sla/', views.configurar_sla_view, name='configurar_sla'),

    # ─── Reportes y Exportación ──────────────────────────────
    path('reportes/', views.reportes_view, name='reportes'),
    path('exportar/excel/', views.exportar_excel_view, name='exportar_excel'),

    # ─── Encuesta CSAT ───────────────────────────────────────
    path('encuesta/<uuid:token>/', views.encuesta_csat_view, name='encuesta_csat'),

    # ─── APIs AJAX ───────────────────────────────────────────
    path('api/buscar-clientes/', views.api_buscar_clientes, name='api_buscar_clientes'),
    path('api/buscar-ciudades/', views.api_buscar_ciudades, name='api_buscar_ciudades'),
    path('api/buscar-cargos/', views.api_buscar_cargos, name='api_buscar_cargos'),
    path('api/buscar-clientes-admin/', views.api_buscar_clientes_admin, name='api_buscar_clientes_admin'),
    path('api/buscar-maestro-instituciones/', views.api_buscar_maestro_instituciones, name='api_buscar_maestro_instituciones'),
    path('api/chat-analitico/', views.api_chat_analitico, name='api_chat_analitico'),
    path('api/ticket/<str:ticket_id>/comentario/', views.api_agregar_comentario, name='api_agregar_comentario'),
    path('api/ticket/<str:ticket_id>/reclasificar/', views.api_reclasificar_ia, name='api_reclasificar_ia'),
    path('api/ticket/<str:ticket_id>/aplicar-reclasificacion/', views.api_aplicar_reclasificacion, name='api_aplicar_reclasificacion'),
    path('api/buscar-tickets/', views.api_buscar_tickets, name='api_buscar_tickets'),
    path('api/simular-rol/', views.api_simular_rol, name='api_simular_rol'),
    path('api/simular-opciones/', views.api_simular_opciones, name='api_simular_opciones'),

    # ─── Monitoreo del Sistema ───────────────────────────────
    path('monitoreo/', views.monitoreo_view, name='monitoreo'),
    path('monitoreo/descargar/<str:tipo>/', views.descargar_log_view, name='descargar_log'),
    path('monitoreo/respaldo-db/', views.descargar_respaldo_db_view, name='descargar_respaldo_db'),

    # ─── Control de Cambios ──────────────────────────────────
    path('control-cambios/', views.control_cambios_view, name='control_cambios'),
    path('control-cambios/api/detalle/<str:commit_hash>/', views.api_detalle_commit, name='api_detalle_commit'),
    path('control-cambios/api/diff/<str:commit_hash>/', views.api_diff_commit, name='api_diff_commit'),
    path('control-cambios/api/revertir/<str:commit_hash>/', views.api_revertir_commit, name='api_revertir_commit'),
]
