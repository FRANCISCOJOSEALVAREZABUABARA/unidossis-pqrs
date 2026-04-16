import os
import sys

# Append the directory of the project
sys.path.append(r"c:\Users\Francisco Alvarez\App_PQRS_Unidossis\unidossis_pqrs")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'unidossis_pqrs.settings')

import django
try:
    django.setup()
    print("Django setup successful!")
except Exception as e:
    import traceback
    traceback.print_exc()
