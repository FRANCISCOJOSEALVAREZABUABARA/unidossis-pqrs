import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unidossis_pqrs.settings')
django.setup()

from django.contrib.auth.models import User
from tickets.models import PerfilUsuario

def list_users():
    print(f"{'Username':<20} | {'Role':<20} | {'Regional':<20}")
    print("-" * 65)
    for user in User.objects.all():
        try:
            perfil = user.perfil
            rol = perfil.rol
            regional = perfil.regional or "N/A"
        except PerfilUsuario.DoesNotExist:
            rol = "No Profile"
            regional = "N/A"
        
        print(f"{user.username:<20} | {rol:<20} | {regional:<20}")

if __name__ == "__main__":
    list_users()
