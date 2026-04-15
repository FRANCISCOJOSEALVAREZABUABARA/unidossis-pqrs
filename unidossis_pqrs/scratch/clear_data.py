import os
import shutil
from django.conf import settings
from django.contrib.auth.models import User
from tickets.models import Ticket, Cliente, Ciudad, Cargo, ArchivoAdjunto

def clear_all_data():
    print("Iniciando limpieza de base de datos...")

    # 1. Borrar Tickets y Adjuntos
    count_tickets = Ticket.objects.count()
    Ticket.objects.all().delete()
    print(f"- {count_tickets} Tickets eliminados.")

    count_adjuntos = ArchivoAdjunto.objects.count()
    ArchivoAdjunto.objects.all().delete()
    print(f"- {count_adjuntos} Registros de archivos eliminados.")

    # 2. Borrar archivos físicos en media
    media_path = os.path.join(settings.MEDIA_ROOT, 'adjuntos_pqrs')
    if os.path.exists(media_path):
        shutil.rmtree(media_path)
        os.makedirs(media_path)
        print(f"- Archivos físicos en {media_path} eliminados.")

    # 3. Borrar Clientes y sus usuarios
    # Ojo: Solo borrar usuarios que NO sean staff ni superuser
    usuarios_borrados = User.objects.filter(is_staff=False, is_superuser=False).delete()
    print(f"- {usuarios_borrados[0]} Usuarios de clientes eliminados.")

    count_clientes = Cliente.objects.count()
    Cliente.objects.all().delete()
    print(f"- {count_clientes} Clientes eliminados.")

    # 4. Borrar Maestros
    count_ciudades = Ciudad.objects.count()
    Ciudad.objects.all().delete()
    print(f"- {count_ciudades} Ciudades eliminadas.")

    count_cargos = Cargo.objects.count()
    Cargo.objects.all().delete()
    print(f"- {count_cargos} Cargos eliminados.")

    print("Limpieza completada exitosamente.")

if __name__ == "__main__":
    clear_all_data()
