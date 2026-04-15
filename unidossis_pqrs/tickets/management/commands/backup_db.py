"""
Backup automático de la base de datos SQLite.
Uso: python manage.py backup_db
Mantiene los últimos 7 backups y elimina los más antiguos.
"""
import os
import shutil
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Crea un backup de la base de datos SQLite y mantiene los últimos 7'

    def add_arguments(self, parser):
        parser.add_argument('--max-backups', type=int, default=7,
                            help='Número máximo de backups a mantener (default: 7)')

    def handle(self, *args, **options):
        max_backups = options['max_backups']
        db_path = settings.DATABASES['default']['NAME']

        if not os.path.exists(db_path):
            self.stdout.write(self.style.ERROR(f'❌ Base de datos no encontrada: {db_path}'))
            return

        # Crear directorio de backups
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        # Generar nombre del backup
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_name = f'db_{timestamp}.sqlite3'
        backup_path = os.path.join(backup_dir, backup_name)

        # Copiar la base de datos
        try:
            shutil.copy2(str(db_path), backup_path)
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            self.stdout.write(self.style.SUCCESS(
                f'✅ Backup creado: {backup_name} ({size_mb:.2f} MB)'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error al crear backup: {e}'))
            return

        # Limpiar backups antiguos
        backups = sorted([
            f for f in os.listdir(backup_dir)
            if f.startswith('db_') and f.endswith('.sqlite3')
        ])

        if len(backups) > max_backups:
            backups_a_eliminar = backups[:len(backups) - max_backups]
            for old_backup in backups_a_eliminar:
                old_path = os.path.join(backup_dir, old_backup)
                os.remove(old_path)
                self.stdout.write(f'  🗑️ Eliminado backup antiguo: {old_backup}')

        # Resumen
        backups_actuales = [f for f in os.listdir(backup_dir) if f.endswith('.sqlite3')]
        self.stdout.write(f'\n📁 Backups en disco: {len(backups_actuales)} (máximo: {max_backups})')
        self.stdout.write(f'📂 Ubicación: {backup_dir}')
