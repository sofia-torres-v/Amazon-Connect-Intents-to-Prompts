# Versión con intents (Amazon Lex V2)

← [Volver al README principal](../README.md)

En esta versión, un bot de Amazon Lex V2 detecta qué quiere el cliente (intent), recoge los datos que faltan (slots) y llama a una función Lambda para ejecutar la operación sobre DynamoDB.

<div align="center">
<img src="assets/arquitectura-bot.png" alt="Arquitectura de la versión con intents" width="100%" />
</div>

## Cómo funciona

1. El cliente escribe en el chat de Amazon Connect.
2. El bot de Lex detecta el intent y pregunta, uno por uno, los slots que faltan.
3. Cuando tiene los datos, Lex invoca la Lambda (fulfillment) con el intent y los valores de los slots.
4. La Lambda ejecuta la operación y responde a Lex con el mensaje para el cliente.

## Cómo reproducirla

1. Crea las tablas de DynamoDB: [tablas-dynamodb.md](../docs/tablas-dynamodb.md).
2. Crea la función Lambda con el código de esta carpeta (ver la sección "La Lambda" más abajo).
3. Crea el bot de Lex con los intents y slots de la siguiente sección y asigna la Lambda como fulfillment.
4. Conecta el bot a Amazon Connect (ver "Cómo conectarlo a Amazon Connect").
5. Si algo falla, revisa [troubleshooting](../docs/troubleshooting.md).

## Intents y slots

| Intent | Qué hace | Slots que usa |
|---|---|---|
| `AgendarCitaIntent` | Agenda una cita | `documento`, `especialidad`, `fecha`, `hora`, `paciente` |
| `ConsultarCitaIntent` | Consulta la cita de un paciente | `documento` |
| `CancelarCitaIntent` | Cancela una cita | `codigo_cita` |
| `ConsultarDisponibilidadIntent` | Muestra horarios libres | `especialidad`, `fecha` |
| `ReagendarCitaIntent` | Cambia fecha y hora de una cita | `codigo_cita`, `fecha`, `hora` |

Los nombres de intents y slots son los que la Lambda espera. Si los cambias en Lex, cámbialos también en el código.

### Capturas de la configuración

![Lista de bots de Lex](assets/lex-bots.png)

*Bots creados en Amazon Lex V2.*

![Intents del bot de citas](assets/lex-intents.png)

*Los cinco intents del bot.*

![Slots del intent de agendar](assets/lex-slots-agendar.png)

*Slots del intent `AgendarCitaIntent`.*

![Fulfillment con Lambda](assets/lex-fulfillment.png)

*Conexión del bot con la función Lambda.*

## La Lambda

Código: [`lambda_function.py`](lambda_function.py)

- Lee el nombre del intent y los valores de los slots del evento de Lex (`sessionState`).
- Ejecuta la operación que corresponde al intent y devuelve un mensaje.
- Si falta o falla un dato (por ejemplo, un horario ocupado), pide de nuevo ese slot con `ElicitSlot`. Vuelve a preguntar una sola vez (`MAX_REINTENTOS = 1`); después cierra la conversación con el mensaje.
- Valida que el código de cita tenga el formato `CITA-1234` antes de buscarlo.

Configuración de la función:

| Elemento | Valor |
|---|---|
| Variables de entorno | `ESPECIALIDADES_TABLE`, `CITAS_TABLE` (opcionales; tienen valor por defecto) |
| Permisos | Lectura y escritura sobre las dos tablas y sus índices (ver [tablas-dynamodb.md](../docs/tablas-dynamodb.md)) |
| Permiso de invocación | El bot de Lex debe poder invocar la función |

## Prueba de la conversación

El mismo mensaje inicial se probó en las dos versiones:

> Hola, quiero agendar una cita a mi nombre soy la paciente Sol, es urgente la necesito para hoy mismo.

![Conversación con el bot de Lex](assets/chat-lex.png)

Con esta configuración, el bot pide cada dato con su frase fija (documento, nombre del paciente) y no interpreta el mensaje libre como lo hace el agente: aunque el cliente ya haya dicho su nombre, el bot volvió a preguntarlo. Es un comportamiento de esta configuración y de sus reintentos, no una limitación general de Lex.

## Cómo conectarlo a Amazon Connect

El bot de Lex no atiende solo: se usa dentro de un flujo de contacto de Amazon Connect, igual que en la versión con agente.

1. Construye el bot (**Build**) y crea un alias.
2. En el idioma del alias, asigna la Lambda como fulfillment.
3. Asegúrate de que el bot esté habilitado para tu instancia de Amazon Connect, en la configuración de la instancia (sección de Amazon Lex).
4. Crea un flujo de contacto (**Flows → Create flow**) con esta secuencia:
   - **Set logging behavior** (Enabled).
   - Un mensaje de bienvenida.
   - **Get customer input**, seleccionando este bot y su alias.
   - **Disconnect** al final de todos los caminos.
5. Guarda, publica el flujo y pruébalo con **Test chat**.

A diferencia de la versión con agente, este flujo no lleva el bloque **Connect assistant** ni el atributo de sesión con el ARN del agente, porque no usa Amazon Q in Connect.

Ajusta estos pasos a como armaste tu flujo.

## Limitaciones de esta versión

- La lógica de negocio está repetida en esta Lambda y en la de la versión con agente.
- El código de cita se genera al azar sin comprobar que no exista.
- Hay una condición de carrera al agendar. Más detalle en [troubleshooting](../docs/troubleshooting.md).