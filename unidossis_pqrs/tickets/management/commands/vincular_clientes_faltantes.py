"""
Management command para vincular tickets sin cliente a sus clientes del maestro.
Usa búsqueda fuzzy para emparejar nombres similares.

Uso: python manage.py vincular_clientes_faltantes
     python manage.py vincular_clientes_faltantes --aplicar
"""
from django.core.management.base import BaseCommand
from tickets.models import Ticket, Cliente


class Command(BaseCommand):
    help = 'Vincula tickets huérfanos (sin cliente_rel) con el maestro de clientes usando fuzzy match'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true', help='Aplicar cambios (sin esto, solo muestra)')

    def handle(self, *args, **options):
        aplicar = options['aplicar']

        # Tickets sin cliente vinculado pero con entidad_cliente
        tickets_huerfanos = Ticket.objects.filter(
            cliente_rel__isnull=True
        ).exclude(
            entidad_cliente__isnull=True
        ).exclude(
            entidad_cliente=''
        )

        self.stdout.write(f'\n📊 Tickets sin cliente vinculado: {tickets_huerfanos.count()}')

        # Cache de clientes
        clientes = list(Cliente.objects.all())
        self.stdout.write(f'📋 Clientes en maestro: {len(clientes)}\n')

        # Obtener entidades únicas sin vincular
        entidades_unicas = set(tickets_huerfanos.values_list('entidad_cliente', flat=True))
        self.stdout.write(f'🏥 Entidades únicas sin vincular: {len(entidades_unicas)}\n')

        vinculados = 0
        no_encontrados = []

        for entidad in sorted(entidades_unicas):
            entidad_upper = entidad.upper().strip()
            match = None
            tipo_match = ''

            # 1. Match exacto
            for c in clientes:
                if c.nombre.upper().strip() == entidad_upper:
                    match = c
                    tipo_match = 'EXACTO'
                    break

            # 2. Contiene parcial (el nombre del maestro está dentro del de la entidad o viceversa)
            if not match:
                for c in clientes:
                    nombre_db = c.nombre.upper().strip()
                    if nombre_db in entidad_upper or entidad_upper in nombre_db:
                        match = c
                        tipo_match = 'PARCIAL'
                        break

            # 3. Match por palabras clave (al menos 2 palabras significativas coinciden)
            if not match:
                palabras_entidad = set(w for w in entidad_upper.split() if len(w) > 3)
                mejor_score = 0
                for c in clientes:
                    palabras_db = set(w for w in c.nombre.upper().strip().split() if len(w) > 3)
                    coincidencias = len(palabras_entidad & palabras_db)
                    if coincidencias >= 2 and coincidencias > mejor_score:
                        mejor_score = coincidencias
                        match = c
                        tipo_match = f'KEYWORDS({coincidencias})'

            if match:
                count = tickets_huerfanos.filter(entidad_cliente=entidad).count()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✅ [{tipo_match}] "{entidad}" → "{match.nombre}" ({count} tickets)'
                    )
                )
                if aplicar:
                    tickets_huerfanos.filter(entidad_cliente=entidad).update(cliente_rel=match)
                vinculados += count
            else:
                count = tickets_huerfanos.filter(entidad_cliente=entidad).count()
                no_encontrados.append((entidad, count))
                self.stdout.write(
                    self.style.WARNING(f'  ❌ "{entidad}" — SIN MATCH ({count} tickets)')
                )

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'Tickets vinculados: {vinculados}')
        self.stdout.write(f'Entidades sin match: {len(no_encontrados)}')

        if no_encontrados:
            self.stdout.write(f'\n⚠️  Clientes que necesitan crearse en el maestro:')
            for ent, cnt in no_encontrados:
                self.stdout.write(f'    - {ent} ({cnt} tickets)')

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                f'\n⚠️  Modo preview. Para aplicar los cambios, ejecuta:'
            ))
            self.stdout.write('    python manage.py vincular_clientes_faltantes --aplicar\n')
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Cambios aplicados exitosamente.\n'))
