import smtplib
import json
import urllib.request
from email.message import EmailMessage

def simulacro_pqrs():
    print("1. Generando cuenta temporal de pruebas en Ethereal Email...")
    
    try:
        # Llamamos a la API de Ethereal para que nos de un buzón de usar y tirar
        peticion = urllib.request.Request("https://api.nodemailer.com/user", method="POST")
        peticion.add_header('Content-Type', 'application/json')
        respuesta = urllib.request.urlopen(peticion, data=b'{"requestor":"test-script","version":"1.0"}')
        cuenta = json.loads(respuesta.read().decode('utf-8'))
    except Exception as e:
        print("Hubo un error al crear la cuenta:\n", e)
        return

    usuario = cuenta['user']
    contrasena = cuenta['pass']
    
    print("   - Listo. ¡Buzón temporal en línea!")
    print("\n2. Simulando la llegada de un correo de un cliente al sistema de PQRS...")

    # Redactamos el correo de prueba (como si fueramos el cliente enviando la queja)
    correo = EmailMessage()
    correo['Subject'] = '[QUEJA] - Mi pedido no ha llegado'
    correo['From'] = '"Juan Cliente 😠" <juan.cliente@internet.com>'
    correo['To'] = 'pqrs@unidossis.com'
    
    # Contenido del correo en texto enriquecido (HTML)
    correo.set_content("""\
    <html>
      <body>
        <p>Hola,</p>
        <p>Hice un pedido hace 15 días y todavía no recibo nada. <b>Espero pronta respuesta.</b></p>
      </body>
    </html>
    """, subtype='html')

    try:
        # Nos conectamos y enviamos
        with smtplib.SMTP("smtp.ethereal.email", 587) as servidor:
            servidor.starttls() # Habilitar la seguridad
            servidor.login(usuario, contrasena)
            servidor.send_message(correo)
            
        print("   - Correo procesado con éxito y atrapado por nuestra bandeja de pruebas.")
        
        print("\n=======================================================")
        print(" YA PUEDES ENTRAR Y VISUALIZAR EL CORREO COMO SISTEMA ")
        print("   1. Entra al enlace: https://ethereal.email/login")
        print(f"   2. Correo: {usuario}")
        print(f"   3. Clave:  {contrasena}")
        print("=======================================================\n")
        print("Haz clic en 'Messages' arriba en Ethereal y verás la queja tal cual como nosotros la capturaríamos y la procesaríamos por detrás.")

    except Exception as e:
        print(f"Error interno al de simular el envío: {e}")

if __name__ == "__main__":
    simulacro_pqrs()
