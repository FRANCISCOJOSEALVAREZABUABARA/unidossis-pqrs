import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unidossis_pqrs.settings')
django.setup()

from django.contrib.auth.models import User
from tickets.models import PerfilUsuario, Cliente, Ciudad

def create_test_users():
    # Ensure a city exists
    ciudad, _ = Ciudad.objects.get_or_create(nombre="Bogota")

    # 1. Create Cliente User
    client_username = "cliente_test"
    client_pass = "unidossis2026"
    
    client_user, created = User.objects.get_or_create(username=client_username)
    if created or client_user:
        client_user.set_password(client_pass)
        client_user.email = "cliente@test.com"
        client_user.save()
        print(f"User {client_username} updated/created.")

    # Create Cliente Institution
    cliente_inst, created = Cliente.objects.get_or_create(
        nombre="Clinica Test Unidossis",
        defaults={
            'ciudad': ciudad,
            'regional': 'liquidos',
            'email_principal': 'cliente@test.com',
            'user': client_user
        }
    )
    if not created:
        cliente_inst.user = client_user
        cliente_inst.save()
    print(f"Cliente institution {cliente_inst.nombre} linked to {client_username}.")

    # Create Profile for Cliente
    perfil_client, created = PerfilUsuario.objects.get_or_create(
        user=client_user,
        defaults={
            'rol': 'cliente',
            'cliente': cliente_inst
        }
    )
    if not created:
        perfil_client.rol = 'cliente'
        perfil_client.cliente = cliente_inst
        perfil_client.save()
    print(f"Profile for {client_username} set as 'cliente'.")

    # 2. Create Regional User
    regional_username = "regional_test"
    regional_pass = "unidossis2026"
    
    reg_user, created = User.objects.get_or_create(username=regional_username)
    if created or reg_user:
        reg_user.set_password(regional_pass)
        reg_user.email = "regional@test.com"
        reg_user.save()
        print(f"User {regional_username} updated/created.")

    # Create Profile for Regional
    perfil_reg, created = PerfilUsuario.objects.get_or_create(
        user=reg_user,
        defaults={
            'rol': 'director_regional',
            'regional': 'occidente'
        }
    )
    if not created:
        perfil_reg.rol = 'director_regional'
        perfil_reg.regional = 'occidente'
        perfil_reg.save()
    print(f"Profile for {regional_username} set as 'director_regional' for 'occidente'.")

if __name__ == "__main__":
    create_test_users()
