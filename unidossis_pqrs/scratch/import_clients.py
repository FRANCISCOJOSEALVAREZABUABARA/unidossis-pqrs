import os
import django
import sys
import openpyxl

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unidossis_pqrs.settings')
django.setup()

from tickets.models import Cliente

excel_path = '../Listado de Cliente_Nombre comercial.xlsx'

def import_clients():
    try:
        wb = openpyxl.load_workbook(excel_path)
        sheet = wb.active
        count = 0
        for row in sheet.iter_rows(min_row=2, values_only=True):
            name = row[0]
            if name and isinstance(name, str):
                name = name.strip()
                if name:
                    obj, created = Cliente.objects.get_or_create(nombre=name)
                    if created:
                        count += 1
        print(f"Éxito: Se han importado {count} clientes nuevos.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import_clients()
