import os
import random
import openpyxl
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.files import File
from tickets.models import Ticket, ArchivoAdjunto
from tickets.ia_engine import analizar_ticket_con_ia
from pathlib import Path
from django.db import transaction

# Textos de quejas genéricas para la simulación
QUEJAS_BASE = [
    ("Retraso en pedido", "Buenos días, mi pedido lleva más de 15 días retrasado y nadie me da respuesta. Exijo una solución INMEDIATA."),
    ("Producto defectuoso", "El empaque llegó roto y aparentemente falta la mitad del contenido. Adjunto las fotos correspondientes."),
    ("Sugerencia de empaque", "Buenas tardes, me encanta su servicio pero creo que podrían usar materiales más ecológicos en las entregas."),
    ("Error en la factura", "La factura que me cobraron este mes está por un valor superior al que había autorizado. Necesito revisión urgente."),
    ("Consulta de disponibilidad", "Hola, me gustaría saber cuándo volverán a tener inventario del producto X que aparece agotado."),
    ("Felicitaciones", "Solo quería escribir para felicitar al equipo de atención al cliente, fueron muy amables resolviendo mi caso anterior."),
    ("Problemas con el portal", "No he podido ingresar con mi usuario al portal de mi cuenta desde hace 3 días, sale error de contraseña."),
    ("Devolución de dinero", "Quiero solicitar la devolución de mi dinero, el servicio no fue lo que esperaba y estoy cancelando todo."),
]

class Command(BaseCommand):
    help = 'Inyecta masivamente 100 PQRS de prueba leyendo el Excel de Clientes'

    RESPONSABLES_MAP = {
        'antioquia': 'James Granada',
        'occidente': 'Angela Parra',
        'costa': 'Maria Victoria',
        'eje_cafetero': 'Leidy Rico',
        'llanos': 'Tatiana Rico',
        'liquidos': 'Martin Durango',
        'solidos': 'Reyes Doria',
        'marly': 'Por Asignar'
    }

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando inyección de datos masiva...")

        # Rutas dinámicas basadas en la confirmación del usuario
        project_root = Path(os.path.abspath(__file__)).parent.parent.parent.parent.parent
        simulacion_dir = project_root / 'simulacion'
        clientes_excel = simulacion_dir / 'CLIENTES.xlsx'
        ejemplos_dir = simulacion_dir / 'EJEMPLOS DE PQRS'

        if not clientes_excel.exists():
            self.stdout.write(self.style.ERROR(f"No se encontró el archivo {clientes_excel}"))
            return

        # 1. Leer clientes desde Excel
        clientes = []
        try:
            workbook = openpyxl.load_workbook(clientes_excel, data_only=True)
            sheet = workbook.active
            # Suponiendo que la Columna A es Nombre y B es Email o parecido, iteraremos
            for row in sheet.iter_rows(min_row=2, values_only=True): # saltamos encabezado
                # Limpiar celdas vacías
                row = [c for c in row if c]
                if len(row) >= 2:
                    clientes.append({"nombre": str(row[0]), "email": str(row[1])})
                elif len(row) == 1:
                    clientes.append({"nombre": "Cliente Excel", "email": str(row[0])})
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"No se pudo leer el Excel: {e}"))
            return

        if not clientes:
            self.stdout.write(self.style.WARNING("El archivo de clientes Excel parece estar vacío o en un formato extraño. Generando clientes automáticos..."))
            for i in range(1, 20):
                clientes.append({"nombre": f"Cliente Generado {i}", "email": f"correo{i}@prueba.com"})

        # 2. Archivos adjuntos documentales
        documentos_físicos = []
        if ejemplos_dir.exists():
            for root, dirs, files in os.walk(ejemplos_dir):
                for file in files:
                    # Incluir todo, en su mayoría docx y pdf confirmados por el usuario
                    documentos_físicos.append(os.path.join(root, file))

        # 3. Limpieza de tickets previos opcional (Comentado o forzado)
        with transaction.atomic():
            Ticket.objects.all().delete()
            self.stdout.write("Limpieza anterior completada. Base de Datos en Cero.")

            # 4. Inyección Aleatoria
            dias_atras = 90
            ahora = timezone.now()
            
            # Textos para Respuesta ficticia de Unidossis
            RESPUESTAS_AGENTES = [
                "Estimado cliente, nos disculpamos por el inconveniente. Ya hemos escalado el problema internamente y hemos emitido el reembolso.",
                "Hola, lamentamos lo sucedido con el envío. Tras verificar con ruta, se estará re-despachando su pedido como compensación.",
                "Gracias por su sugerencia, ha sido enviada al comité de calidad regional de la junta.",
                "Verificamos la facturación y efectivamente hay un cargo mal ejecutado. Adjuntamos nota de crédito de corrección."
            ]

            for i in range(1, 101): # 100 pruebas
                cliente = random.choice(clientes)
                asunto, cuerpo = random.choice(QUEJAS_BASE)
                estado = random.choice([e[0] for e in Ticket.STATUS_CHOICES])
                regional = random.choice([r[0] for r in Ticket.REGIONAL_CHOICES])
                proceso = random.choice([p[0] for p in Ticket.AREA_CHOICES])
                linea = random.choice([l[0] for l in Ticket.LINEA_CHOICES])
                tipificacion = random.choice([t[0] for t in Ticket.TIPIFICACION_CHOICES])
                
                # Generador de fechas
                dias_aleatorios = random.randint(0, dias_atras)
                horas_aleatorias = random.randint(0, 23)
                fecha_falsa = ahora - timedelta(days=dias_aleatorios, hours=horas_aleatorias)

                # Si está cerrado (resuelto) le inventamos respuesta
                respuesta = random.choice(RESPUESTAS_AGENTES) if estado == 'resuelto' else ""

                # Pase del ticket a través de la IA
                resultado_ia = analizar_ticket_con_ia(asunto, cuerpo)

                ticket = Ticket(
                    remitente_nombre=cliente["nombre"],
                    remitente_email=cliente["email"],
                    asunto=asunto,
                    cuerpo=cuerpo,
                    estado=estado,
                    regional=regional,
                    proceso=resultado_ia["proceso"],
                    linea_servicio=resultado_ia["linea"],
                    tipificacion=resultado_ia["tipificacion"],
                    criticidad=resultado_ia.get("criticidad", "informativa"),
                    analisis_ia=resultado_ia["analisis_ia"],
                    clasificado_por_ia=True,
                    responsable=self.RESPONSABLES_MAP.get(regional, 'Sin Asignar'),
                    respuesta_oficial=respuesta
                )
                ticket.save()
                
                Ticket.objects.filter(id=ticket.id).update(fecha_ingreso=fecha_falsa)

                # Injectar anexos físicos al 30% como evidencia del CLIENTE
                if documentos_físicos and random.random() < 0.3:
                    ruta_documento = random.choice(documentos_físicos)
                    try:
                        with open(ruta_documento, 'rb') as f:
                            nombre_archivo = os.path.basename(ruta_documento)
                            adj = ArchivoAdjunto(ticket=ticket, es_respuesta_agente=False)
                            adj.archivo.save(nombre_archivo, File(f), save=True)
                            ArchivoAdjunto.objects.filter(id=adj.id).update(fecha_subida=fecha_falsa)
                    except Exception:
                        pass
                
                # 10% probabilidad de que UNIDOSSIS también mandó un adjunto de respuesta (si el caso está resuelto)
                if estado == 'resuelto' and documentos_físicos and random.random() < 0.1:
                    ruta_doc_agente = random.choice(documentos_físicos)
                    try:
                        with open(ruta_doc_agente, 'rb') as f:
                            nombre_archivo = "Certificado_" + os.path.basename(ruta_doc_agente)
                            adj_agente = ArchivoAdjunto(ticket=ticket, es_respuesta_agente=True)
                            adj_agente.archivo.save(nombre_archivo, File(f), save=True)
                            ArchivoAdjunto.objects.filter(id=adj_agente.id).update(fecha_subida=fecha_falsa + timedelta(days=1))
                    except Exception:
                        pass

            self.stdout.write(self.style.SUCCESS('¡100 tickets con Sedes Asignadas simulados con éxito y esparcidos en el tiempo!'))
