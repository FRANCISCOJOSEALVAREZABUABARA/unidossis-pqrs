const nodemailer = require("nodemailer");

async function simulacroPQRS() {
  console.log("1. Generando cuenta temporal de pruebas en Ethereal Email...");
  const cuentaPrueba = await nodemailer.createTestAccount();

  console.log("   - Listo. Cuenta conectada.");

  // Configuramos nuestra conexión con el servidor falso de pruebas
  const transportador = nodemailer.createTransport({
    host: "smtp.ethereal.email",
    port: 587,
    secure: false, // true para el puerto 465, false para otros
    auth: {
      user: cuentaPrueba.user, 
      pass: cuentaPrueba.pass, 
    },
  });

  console.log("\n2. Simulando la llegada de un correo que envió un cliente (PQRS)...");
  
  // Enviamos el correo simulado
  const informacionCorreo = await transportador.sendMail({
    from: '"Juan Cliente 😠" <juan.cliente@internet.com>', // Quien lo envía
    to: "pqrs@unidossis.com", // A quien va dirigido
    subject: "[QUEJA] - Mi pedido no ha llegado", // Asunto
    text: "Hola, hice un pedido hace 15 días y todavía no recibo nada. Espero pronta respuesta.", 
    html: "<p>Hola,</p><p>Hice un pedido hace 15 días y todavía no recibo nada. <b>Espero pronta respuesta.</b></p>",
  });

  console.log("   - Correo procesado con éxito.");
  console.log("   - ID Interno del mensaje: %s", informacionCorreo.messageId);
  
  // Ethereal nos proporciona un link para "visualizar" esa bandeja falsa
  console.log("\n=======================================================");
  console.log("🌟 HAZ CLIC EN ESTE ENLACE PARA VER EL CORREO RECIBIDO 🌟:");
  console.log("   " + nodemailer.getTestMessageUrl(informacionCorreo));
  console.log("=======================================================\n");
  console.log("Ahí podrás comprobar lo que el sistema vería y cómo procesaremos los mensajes futuros.");
}

simulacroPQRS().catch(console.error);
