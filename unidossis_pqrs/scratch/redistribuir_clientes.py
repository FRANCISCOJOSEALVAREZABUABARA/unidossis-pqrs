import os
import sys
import django
import random

# Agregar el directorio actual al path
sys.path.append(os.getcwd())

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unidossis_pqrs.settings')
django.setup()

from tickets.models import Ticket, Cliente

def redistribute_tickets():
    # Obtener todos los clientes reales
    clientes = list(Cliente.objects.exclude(nombre='(en blanco)'))
    if not clientes:
        print("No hay clientes suficientes para redistribuir.")
        return

    # Buscar tickets con el nombre generico o que necesiten limpieza
    tickets = Ticket.objects.filter(remitente_nombre__icontains='Excel')
    total = tickets.count()
    
    print(f"Iniciando redistribucion de {total} tickets...")
    
    count = 0
    for t in tickets:
        cliente_elegido = random.choice(clientes)
        
        # Actualizar campos del ticket
        t.cliente_rel = cliente_elegido
        t.remitente_nombre = cliente_elegido.nombre
        t.entidad_cliente = cliente_elegido.nombre
        t.institucion = cliente_elegido.nombre
        
        t.save()
        count += 1
        
    print(f"¡Exito! Se han actualizado {count} tickets con nombres de clientes reales (incluyendo Shaio, La Colina, etc.).")

if __name__ == "__main__":
    redistribute_tickets()
