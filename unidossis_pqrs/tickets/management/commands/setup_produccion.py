"""
Comando de gestión: setup_produccion
Prepara la base de datos de producción con el usuario administrador inicial.
Uso: python manage.py setup_produccion
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tickets.models import PerfilUsuario


class Command(BaseCommand):
    help = 'Configura el entorno de producción: crea admin y su perfil de superadmin'

    def handle(self, *args, **options):
        self.stdout.write('🚀 Iniciando configuración de producción...')

        # Crear o actualizar usuario admin
        user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@unidossis.com.co',
                'first_name': 'Admin',
                'last_name': 'Unidossis',
                'is_staff': True,
                'is_superuser': True,
            }
        )

        if created:
            user.set_password('Unidossis2025*')
            user.save()
            self.stdout.write(self.style.SUCCESS('✅ Usuario admin creado'))
        else:
            # Asegurarse que tiene los datos correctos
            user.first_name = 'Admin'
            user.last_name = 'Unidossis'
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.WARNING('ℹ️  Usuario admin ya existía — actualizado'))

        # Crear o actualizar perfil superadmin
        perfil, p_created = PerfilUsuario.objects.get_or_create(
            user=user,
            defaults={'rol': 'superadmin'}
        )

        if not p_created:
            perfil.rol = 'superadmin'
            perfil.save()

        self.stdout.write(self.style.SUCCESS('✅ Perfil superadmin configurado'))
        self.stdout.write(self.style.SUCCESS('🎉 Producción lista. Usuario: admin | Pass: Unidossis2025*'))
