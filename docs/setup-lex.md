|# Configuración del bot de Lex y su conexión a Amazon Connect (versión con intents)

← [Volver al README principal](../README.md)

Estos pasos se realizan manualmente desde la consola de AWS. Los nombres de los menús pueden variar un poco según la versión de la consola.

Antes de empezar, necesitas las tablas de DynamoDB ([tablas-dynamodb.md](tablas-dynamodb.md)) y la función Lambda con el código de [`lex-intents/lambda_function.py`](../lex-intents/lambda_function.py). Para la versión con agente, consulta [setup-agente.md](setup-agente.md).

---

## 1. Crear el bot

![Lista de bots de Lex](assets/lex-bots.png)

1. En la consola de AWS, abre **Amazon Lex**.
2. Ve a **Bots → Create bot** y elige crear un bot en blanco.
3. Ponle nombre y deja que Lex cree un rol de IAM con los permisos básicos.
4. Elige el idioma en el que vas a conversar con el cliente (español).

---

## 2. Crear los intents

![Intents del bot de citas](assets/lex-intents.png)

En el idioma del bot, agrega estos cinco intents. Los nombres deben ser exactamente estos, porque la Lambda decide qué operación ejecutar según el nombre del intent:

| Intent | Qué hace |
|---|---|
| `AgendarCitaIntent` | Agenda una cita |
| `ConsultarCitaIntent` | Consulta la cita de un paciente |
| `CancelarCitaIntent` | Cancela una cita |
| `ConsultarDisponibilidadIntent` | Muestra horarios libres |
| `ReagendarCitaIntent` | Cambia fecha y hora de una cita |

A cada intent agrégale **sample utterances**, las frases con las que el cliente suele pedir esa operación. Es lo que Lex usa para reconocer el intent.

---

## 3. Crear los slots

![Slots del intent de agendar](assets/lex-slots-agendar.png)

Cada intent pide los datos que le faltan mediante slots. Los nombres deben coincidir con los que lee la Lambda:

| Intent | Slots |
|---|---|
| `AgendarCitaIntent` | `documento`, `paciente`, `especialidad`, `fecha`, `hora` |
| `ConsultarCitaIntent` | `documento` |
| `CancelarCitaIntent` | `codigo_cita` |
| `ConsultarDisponibilidadIntent` | `especialidad`, `fecha` |
| `ReagendarCitaIntent` | `codigo_cita`, `fecha`, `hora` |

Para cada slot configura:

- El **tipo de slot**, que define qué valores acepta Lex (la captura de arriba muestra los que se usaron).
- El **prompt**, la pregunta que Lex hace al cliente para pedir ese dato.
- Si es **requerido**.

Un detalle importante: la Lambda solo pasa la especialidad a minúsculas y la busca tal cual en DynamoDB. Por eso el slot `especialidad` debe devolver el nombre exacto, sin tilde (por ejemplo `pediatria`), como está guardado en la tabla.

---

## 4. Conectar la Lambda como fulfillment

1. Crea una **versión** del bot y un **alias**.

![Detalles de la versión y alias del bot](assets/lex-version-details.png)

2. En el alias, abre el idioma y asigna la función Lambda.

![Configuración del idioma en el alias asignando la función Lambda](assets/lex-alias-language-support.png)

3. En cada intent, activa el uso de la Lambda para el fulfillment.

![Activación del fulfillment como activo en el intent](assets/lex-fulfillment-active.png)

4. Comprueba que Lex tenga permiso para invocar la función. Normalmente la consola lo agrega al asignarla.

![Políticas de permisos de IAM asociados para la invocación](assets/lex-iam-permissions.png)

La Lambda responde a Lex de dos formas: pide de nuevo un slot (`ElicitSlot`) o cierra la conversación con el mensaje final (`Close`). Vuelve a preguntar un slot una sola vez.
---

## 5. Construir el bot

Haz clic en **Build**. Cuando termine, puedes probarlo desde el panel de prueba de Lex antes de conectarlo a Connect.

---

## 6. Conectar el bot a Amazon Connect

![Flujo de contacto de la versión con Lex](assets/contact-flow-lex.png)

1. Asegúrate de que el bot esté habilitado para tu instancia de Amazon Connect, en la configuración de la instancia (sección de Amazon Lex).
2. Ve a **Flows → Create flow** y conecta los bloques en esta secuencia:

| # | Bloque | Configuración |
|---|---|---|
| 1 | **Set logging behavior** | Enabled |
| 2 | **Mensaje de bienvenida** | El saludo inicial del asistente |
| 3 | **Get customer input** | Selecciona el bot de Lex y su alias |
| 4 | **Disconnect** | Finalización de todos los caminos |

3. Guarda, publica el flujo y pruébalo con **Test chat**.

A diferencia de la versión con agente, este flujo no lleva el bloque **Connect assistant** ni el atributo de sesión con el ARN del agente, porque no usa Amazon Q in Connect.

---

## 7. Probar

Usa el mismo mensaje inicial que en la versión con agente, para poder comparar:

> Hola, quiero agendar una cita a mi nombre soy la paciente Sol, es urgente la necesito para hoy mismo.

Si algo falla, revisa [troubleshooting](troubleshooting.md).

---

[← Volver al README principal](../README.md)