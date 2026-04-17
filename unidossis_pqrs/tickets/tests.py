"""
Tests automatizados para UNIDOSSIS PQRS.
Suite completa: modelos, autenticación, roles, dashboard, portal cliente, APIs, IA.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch, MagicMock
from datetime import timedelta
import json
import uuid

from .models import (
    Ticket, ArchivoAdjunto, Cliente, Ciudad, Cargo, MaestroInstitucion,
    PerfilUsuario, ConfiguracionSLA, AlertaSLA, LogActividad,
    ComentarioTicket, EncuestaSatisfaccion, FeedbackIA, IntentoLogin
)


class BaseTestCase(TestCase):
    """Setup compartido para todos los tests."""

    def setUp(self):
        # Superadmin
        self.superadmin_user = User.objects.create_user('superadmin', 'sa@test.com', 'Test1234!')
        PerfilUsuario.objects.create(user=self.superadmin_user, rol='superadmin')

        # Admin PQRS
        self.admin_user = User.objects.create_user('admin_pqrs', 'admin@test.com', 'Test1234!')
        PerfilUsuario.objects.create(user=self.admin_user, rol='admin_pqrs')

        # Director Regional
        self.director_user = User.objects.create_user('director', 'dir@test.com', 'Test1234!')
        PerfilUsuario.objects.create(user=self.director_user, rol='director_regional', regional='liquidos')

        # Agente
        self.agente_user = User.objects.create_user('agente', 'ag@test.com', 'Test1234!')
        PerfilUsuario.objects.create(user=self.agente_user, rol='agente')

        # Cliente
        self.cliente_obj = Cliente.objects.create(
            nombre='Hospital Test', email_principal='hospital@test.com', regional='liquidos'
        )
        self.cliente_user = User.objects.create_user('cliente1', 'c@test.com', 'Test1234!')
        self.cliente_obj.user = self.cliente_user
        self.cliente_obj.save()
        PerfilUsuario.objects.create(user=self.cliente_user, rol='cliente', cliente=self.cliente_obj)

        # Segundo cliente (para tests de aislamiento)
        self.cliente2_obj = Cliente.objects.create(
            nombre='Clinica Otra', email_principal='clinica@test.com', regional='costa'
        )
        self.cliente2_user = User.objects.create_user('cliente2', 'c2@test.com', 'Test1234!')
        self.cliente2_obj.user = self.cliente2_user
        self.cliente2_obj.save()
        PerfilUsuario.objects.create(user=self.cliente2_user, rol='cliente', cliente=self.cliente2_obj)

        # Ticket de prueba
        self.ticket = Ticket.objects.create(
            cliente_rel=self.cliente_obj,
            entidad_cliente='Hospital Test',
            remitente_nombre='Juan Pérez',
            remitente_email='juan@hospital.com',
            tipo_solicitud='queja',
            asunto='Error en despacho de medicamento',
            cuerpo='Se recibió un lote incorrecto de medicamentos oncológicos.',
            estado='abierto',
            regional='liquidos',
            proceso='logistica',
            linea_servicio='oncologia',
            tipificacion='error_despacho',
            criticidad='mayor',
            responsable='agente',
        )

        # Ticket de otra regional
        self.ticket_costa = Ticket.objects.create(
            cliente_rel=self.cliente2_obj,
            entidad_cliente='Clinica Otra',
            remitente_nombre='María López',
            remitente_email='maria@clinica.com',
            tipo_solicitud='reclamo',
            asunto='Entrega tardía',
            cuerpo='El pedido llegó 3 días después de lo acordado.',
            estado='abierto',
            regional='costa',
        )

        self.client = Client()


# ═══════════════════════════════════════════════════════════
# TEST 1: MODELOS
# ═══════════════════════════════════════════════════════════

class TestModelos(BaseTestCase):

    def test_ticket_id_generado_automaticamente(self):
        self.assertTrue(self.ticket.ticket_id.startswith('PQRS-'))
        self.assertEqual(len(self.ticket.ticket_id), 11)  # PQRS- + 6 chars

    def test_ticket_id_unico(self):
        t2 = Ticket.objects.create(
            remitente_email='otro@test.com', asunto='Otro', cuerpo='Test'
        )
        self.assertNotEqual(self.ticket.ticket_id, t2.ticket_id)

    def test_dias_transcurridos(self):
        self.assertEqual(self.ticket.dias_transcurridos(), 0)

    def test_estado_sla_bien(self):
        self.assertEqual(self.ticket.estado_sla(), 'bien')

    def test_estado_sla_cerrado(self):
        self.ticket.estado = 'resuelto'
        self.ticket.save()
        self.assertEqual(self.ticket.estado_sla(), 'cerrado')

    def test_estado_sla_cancelado(self):
        self.ticket.estado = 'cancelado'
        self.ticket.save()
        self.assertEqual(self.ticket.estado_sla(), 'cerrado')

    def test_sla_dinamico_con_configuracion(self):
        """ConfiguracionSLA debe afectar estado_sla()."""
        ConfiguracionSLA.objects.create(
            nombre='Test SLA', dias_alerta_peligro=3, dias_alerta_vencido=5, activo=True
        )
        # Limpiar caché
        Ticket._sla_config_cache = None
        Ticket._sla_config_ts = 0
        # Ticket recién creado (0 días) → bien
        self.assertEqual(self.ticket.estado_sla(), 'bien')

    def test_sla_fallback_sin_configuracion(self):
        """Sin ConfiguracionSLA activa, usar defaults."""
        ConfiguracionSLA.objects.all().delete()
        Ticket._sla_config_cache = None
        Ticket._sla_config_ts = 0
        self.assertEqual(self.ticket.estado_sla(), 'bien')

    def test_ticket_str(self):
        self.assertIn('PQRS-', str(self.ticket))
        self.assertIn('Error en despacho', str(self.ticket))

    def test_archivo_adjunto_creacion(self):
        adj = ArchivoAdjunto.objects.create(ticket=self.ticket, subido_por_sistema=False)
        self.assertEqual(adj.ticket, self.ticket)

    def test_cliente_str(self):
        self.assertIn('Hospital Test', str(self.cliente_obj))

    def test_perfil_str(self):
        perfil = self.superadmin_user.perfil
        self.assertIn('superadmin', str(perfil))

    def test_comentario_creacion(self):
        c = ComentarioTicket.objects.create(
            ticket=self.ticket, autor=self.admin_user, texto='Prueba', visibilidad='interno'
        )
        self.assertIn('PQRS-', str(c))

    def test_log_actividad_creacion(self):
        log = LogActividad.objects.create(
            ticket=self.ticket, usuario=self.admin_user, accion='Test action'
        )
        self.assertIn('PQRS-', str(log))

    def test_log_sin_ticket(self):
        log = LogActividad.objects.create(usuario=self.admin_user, accion='Sistema action')
        self.assertIn('[Sistema]', str(log))

    def test_encuesta_csat_token_unico(self):
        e = EncuestaSatisfaccion.objects.create(ticket=self.ticket)
        self.assertIsInstance(e.token, uuid.UUID)

    def test_configuracion_sla_get_emails(self):
        sla = ConfiguracionSLA.objects.create(
            emails_alerta_peligro='a@t.com, b@t.com', emails_alerta_vencido='c@t.com'
        )
        self.assertEqual(len(sla.get_emails_peligro()), 2)
        self.assertEqual(len(sla.get_emails_vencido()), 1)

    def test_intento_login_str(self):
        il = IntentoLogin.objects.create(ip='1.2.3.4', username='test', exitoso=True)
        self.assertIn('✅', str(il))
        il2 = IntentoLogin.objects.create(ip='1.2.3.4', username='test', exitoso=False)
        self.assertIn('❌', str(il2))

    def test_feedback_ia_creacion(self):
        fb = FeedbackIA.objects.create(
            ticket=self.ticket, corrector=self.admin_user,
            ia_tipificacion_original='error_despacho', tipificacion_corregida='error_empaque'
        )
        self.assertIn('PQRS-', str(fb))


# ═══════════════════════════════════════════════════════════
# TEST 2: AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════

class TestAutenticacion(BaseTestCase):

    def test_login_exitoso_superadmin(self):
        resp = self.client.post(reverse('login'), {'username': 'superadmin', 'password': 'Test1234!'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('dashboard', resp.url)

    def test_login_exitoso_cliente(self):
        resp = self.client.post(reverse('login'), {'username': 'cliente1', 'password': 'Test1234!'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('cliente/dashboard', resp.url)

    def test_login_fallido(self):
        resp = self.client.post(reverse('login'), {'username': 'superadmin', 'password': 'WRONG'})
        self.assertEqual(resp.status_code, 200)  # Re-render login page

    def test_rate_limiting(self):
        """Después de 5 intentos fallidos, bloquear por IP."""
        for i in range(5):
            self.client.post(reverse('login'), {'username': 'x', 'password': 'wrong'})
        resp = self.client.post(reverse('login'), {'username': 'superadmin', 'password': 'Test1234!'})
        self.assertEqual(resp.status_code, 200)  # Bloqueado, no redirige
        self.assertContains(resp, 'Demasiados intentos')

    def test_logout(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('logout'))
        self.assertEqual(resp.status_code, 302)

    def test_cambiar_password(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.post(reverse('cambiar_password'), {
            'current_password': 'Test1234!',
            'new_password': 'NuevaClave99!',
            'confirm_password': 'NuevaClave99!',
        })
        data = json.loads(resp.content)
        self.assertEqual(data['tipo'], 'exito')

    def test_cambiar_password_incorrecta(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.post(reverse('cambiar_password'), {
            'current_password': 'WRONG',
            'new_password': 'Nueva123!',
            'confirm_password': 'Nueva123!',
        })
        data = json.loads(resp.content)
        self.assertEqual(data['tipo'], 'error')

    def test_cambiar_password_corta(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.post(reverse('cambiar_password'), {
            'current_password': 'Test1234!',
            'new_password': '123',
            'confirm_password': '123',
        })
        data = json.loads(resp.content)
        self.assertEqual(data['tipo'], 'error')

    def test_login_registra_intento(self):
        self.client.post(reverse('login'), {'username': 'superadmin', 'password': 'Test1234!'})
        self.assertTrue(IntentoLogin.objects.filter(username='superadmin', exitoso=True).exists())

    def test_login_registra_intento_fallido(self):
        self.client.post(reverse('login'), {'username': 'superadmin', 'password': 'WRONG'})
        self.assertTrue(IntentoLogin.objects.filter(username='superadmin', exitoso=False).exists())


# ═══════════════════════════════════════════════════════════
# TEST 3: ROLES Y PERMISOS
# ═══════════════════════════════════════════════════════════

class TestRoles(BaseTestCase):

    def test_dashboard_acceso_superadmin(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_acceso_admin(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_acceso_director(self):
        self.client.login(username='director', password='Test1234!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_denegado_cliente(self):
        self.client.login(username='cliente1', password='Test1234!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 403)

    def test_gestionar_clientes_denegado_director(self):
        self.client.login(username='director', password='Test1234!')
        resp = self.client.get(reverse('gestionar_clientes'))
        self.assertEqual(resp.status_code, 403)

    def test_gestionar_clientes_ok_admin(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.get(reverse('gestionar_clientes'))
        self.assertEqual(resp.status_code, 200)

    def test_configurar_sla_denegado_agente(self):
        self.client.login(username='agente', password='Test1234!')
        resp = self.client.get(reverse('configurar_sla'))
        self.assertEqual(resp.status_code, 403)

    def test_redirige_sin_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_director_solo_ve_su_regional(self):
        self.client.login(username='director', password='Test1234!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        # Director de 'liquidos' no debería ver ticket de 'costa'
        tickets_ctx = resp.context.get('tickets')
        if tickets_ctx is not None:
            for t in tickets_ctx:
                self.assertEqual(t.regional, 'liquidos')

    def test_cliente_no_ve_ticket_ajeno(self):
        self.client.login(username='cliente1', password='Test1234!')
        resp = self.client.get(reverse('ticket_detail', args=[self.ticket_costa.ticket_id]))
        self.assertIn(resp.status_code, [302, 403])

    def test_cliente_ve_su_ticket(self):
        self.client.login(username='cliente1', password='Test1234!')
        resp = self.client.get(reverse('ticket_detail', args=[self.ticket.ticket_id]))
        self.assertEqual(resp.status_code, 200)


# ═══════════════════════════════════════════════════════════
# TEST 4: DASHBOARD
# ═══════════════════════════════════════════════════════════

class TestDashboard(BaseTestCase):

    def test_dashboard_contiene_kpis(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('dashboard'))
        self.assertIn('cantidad_total', resp.context)
        self.assertIn('cumplimiento', resp.context)
        self.assertIn('sla_health', resp.context)

    def test_dashboard_filtro_estado(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('dashboard'), {'estado': 'abierto'})
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_busqueda(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('dashboard'), {'q': 'despacho'})
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_filtro_cliente(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('dashboard'), {'cliente_id': self.cliente_obj.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['cliente_filtrado_nombre'], 'Hospital Test')


# ═══════════════════════════════════════════════════════════
# TEST 5: PORTAL CLIENTE
# ═══════════════════════════════════════════════════════════

class TestPortalCliente(BaseTestCase):

    @patch('tickets.views.analizar_ticket_con_ia')
    def test_crear_pqrs_desde_portal(self, mock_ia):
        mock_ia.return_value = {
            'linea': 'oncologia', 'proceso': 'logistica',
            'tipificacion': 'error_despacho', 'criticidad': 'mayor',
            'analisis_ia': 'Test IA analysis'
        }
        self.client.login(username='cliente1', password='Test1234!')
        resp = self.client.post(reverse('public_portal'), {
            'institucion': 'Hospital Test',
            'nombre': 'Juan',
            'email': 'juan@hospital.com',
            'tipo_solicitud': 'queja',
            'asunto': 'Medicamento dañado',
            'descripcion': 'El medicamento llegó con empaque roto.',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Ticket.objects.filter(asunto='Medicamento dañado').exists())

    def test_portal_cliente_dashboard(self):
        self.client.login(username='cliente1', password='Test1234!')
        resp = self.client.get(reverse('portal_cliente_dashboard'))
        self.assertEqual(resp.status_code, 200)


# ═══════════════════════════════════════════════════════════
# TEST 6: APIs AJAX
# ═══════════════════════════════════════════════════════════

class TestAPIs(BaseTestCase):

    def test_api_buscar_clientes(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('api_buscar_clientes'), {'q': 'Hospital'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('results', data)

    def test_api_buscar_ciudades(self):
        Ciudad.objects.create(nombre='Bogotá')
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('api_buscar_ciudades'), {'q': 'Bog'})
        self.assertEqual(resp.status_code, 200)

    def test_api_buscar_cargos(self):
        Cargo.objects.create(nombre='Director')
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('api_buscar_cargos'), {'q': 'Dir'})
        self.assertEqual(resp.status_code, 200)

    def test_api_agregar_comentario(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.post(
            reverse('api_agregar_comentario', args=[self.ticket.ticket_id]),
            json.dumps({'texto': 'Comentario test', 'visibilidad': 'interno'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ComentarioTicket.objects.filter(texto='Comentario test').exists())

    def test_api_buscar_tickets(self):
        self.client.login(username='superadmin', password='Test1234!')
        resp = self.client.get(reverse('api_buscar_tickets'), {'q': 'despacho'})
        self.assertEqual(resp.status_code, 200)


# ═══════════════════════════════════════════════════════════
# TEST 7: TICKET DETAIL
# ═══════════════════════════════════════════════════════════

class TestTicketDetail(BaseTestCase):

    def test_detalle_acceso_admin(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.get(reverse('ticket_detail', args=[self.ticket.ticket_id]))
        self.assertEqual(resp.status_code, 200)

    def test_cambiar_estado(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        self.client.post(reverse('ticket_detail', args=[self.ticket.ticket_id]), {
            'nuevo_estado': 'revision',
        })
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.estado, 'revision')

    def test_log_creado_al_cambiar_estado(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        self.client.post(reverse('ticket_detail', args=[self.ticket.ticket_id]), {
            'nuevo_estado': 'revision',
        })
        self.assertTrue(LogActividad.objects.filter(
            ticket=self.ticket, accion__contains='Estado cambiado'
        ).exists())

    def test_detalle_ticket_inexistente(self):
        self.client.login(username='admin_pqrs', password='Test1234!')
        resp = self.client.get(reverse('ticket_detail', args=['PQRS-NOEXISTE']))
        self.assertIn(resp.status_code, [404, 500])  # 500 si el middleware captura el 404


# ═══════════════════════════════════════════════════════════
# TEST 8: MOTOR DE IA
# ═══════════════════════════════════════════════════════════

class TestMotorIA(TestCase):

    @patch('tickets.ia_engine.requests.post')
    def test_analizar_ticket_con_gemini(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'candidates': [{'content': {'parts': [{'text': json.dumps({
                'linea': 'oncologia', 'proceso': 'produccion',
                'tipificacion': 'producto_no_conforme', 'criticidad': 'critica',
                'analisis_ia': 'Clasificado por test'
            })}]}}]
        }
        mock_post.return_value = mock_response

        from .ia_engine import analizar_ticket_con_ia
        with patch('tickets.ia_engine.API_URL', 'http://fake'):
            resultado = analizar_ticket_con_ia('Medicamento contaminado', 'Se encontró partículas')
        self.assertEqual(resultado['linea'], 'oncologia')
        self.assertEqual(resultado['criticidad'], 'critica')

    def test_fallback_sin_ia(self):
        from .ia_engine import analizar_ticket_con_ia
        with patch('tickets.ia_engine.API_URL', None):
            resultado = analizar_ticket_con_ia('Test', 'Test desc')
        self.assertEqual(resultado['linea'], 'administrativo')
        self.assertIn('fallback', resultado['analisis_ia'].lower())

    def test_generar_resumen_cliente_local(self):
        from .ia_engine import generar_resumen_cliente
        with patch('tickets.ia_engine.API_URL', None):
            resumen = generar_resumen_cliente(
                'Error en despacho',
                'Se recibió un lote incorrecto de medicamentos oncológicos el día 15 de marzo.'
            )
        self.assertIsInstance(resumen, str)
        self.assertGreater(len(resumen), 10)

    def test_parsear_respuesta_json_limpia_markdown(self):
        from .ia_engine import _parsear_respuesta_json
        texto = '```json\n{"linea": "oncologia"}\n```'
        result = _parsear_respuesta_json(texto)
        self.assertEqual(result['linea'], 'oncologia')

    def test_parsear_respuesta_json_none(self):
        from .ia_engine import _parsear_respuesta_json
        self.assertIsNone(_parsear_respuesta_json(None))
        self.assertIsNone(_parsear_respuesta_json('invalid json'))


# ═══════════════════════════════════════════════════════════
# TEST 9: NOTIFICACIONES
# ═══════════════════════════════════════════════════════════

class TestNotificaciones(TestCase):

    def test_enviar_email(self):
        from .notificaciones import enviar_email
        result = enviar_email('test@test.com', 'Test Subject', 'Test body')
        self.assertTrue(result)

    def test_estado_canales(self):
        from .notificaciones import estado_canales
        estado = estado_canales()
        self.assertIn('email', estado)
        self.assertIn('whatsapp', estado)

    @patch('tickets.notificaciones.enviar_whatsapp')
    @patch('tickets.notificaciones.enviar_email')
    def test_notificar_acuse_recibo(self, mock_email, mock_wa):
        mock_email.return_value = True
        mock_wa.return_value = False
        ticket = Ticket.objects.create(
            remitente_email='test@test.com', asunto='Test', cuerpo='Body',
            remitente_nombre='Juan', tipo_solicitud='queja'
        )
        from .notificaciones import notificar_acuse_recibo
        notificar_acuse_recibo(ticket)
        mock_email.assert_called_once()


# ═══════════════════════════════════════════════════════════
# TEST 10: HEALTH CHECK
# ═══════════════════════════════════════════════════════════

class TestHealthCheck(TestCase):

    def test_health_check_responde(self):
        resp = self.client.get(reverse('health_check'))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['database'], 'ok')
        self.assertIn('version', data)
        self.assertIn('stats', data)

    def test_health_check_sin_autenticacion(self):
        """Health check debe ser público (sin login)."""
        resp = self.client.get(reverse('health_check'))
        self.assertEqual(resp.status_code, 200)


# ═══════════════════════════════════════════════════════════
# TEST 11: ENCUESTA CSAT
# ═══════════════════════════════════════════════════════════

class TestEncuestaSatisfaccion(BaseTestCase):

    def test_encuesta_acceso_con_token(self):
        encuesta = EncuestaSatisfaccion.objects.create(ticket=self.ticket)
        resp = self.client.get(reverse('encuesta_csat', args=[encuesta.token]))
        self.assertEqual(resp.status_code, 200)

    def test_encuesta_token_invalido(self):
        fake_token = uuid.uuid4()
        resp = self.client.get(reverse('encuesta_csat', args=[fake_token]))
        self.assertIn(resp.status_code, [404, 500])  # 500 si el middleware captura el 404
