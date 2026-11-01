# Troubleshooting, flujo de pruebas y limitaciones

← [Volver al README principal](../README.md)

## 1. Flujo de pruebas recomendado (Test Chat)

Puedes probar el asistente de punta a punta desde la consola de Amazon Connect con Test Chat. Estas pruebas aplican a la versión con agente.

### 1.1 Saludo inicial

Cliente: `hola`

Resultado esperado: el agente responde con un saludo amigable y comienza la interacción.

### 1.2 Consulta de catálogo

Cliente: `¿qué especialidades hay?`

Resultado esperado: el agente lista únicamente las cinco especialidades disponibles:

- medicina general
- pediatria
- odontologia
- dermatologia
- oftalmologia

### 1.3 Consulta de disponibilidad

Cliente: `disponibilidad de odontologia para mañana`

Resultado esperado: el agente identifica la acción `consultar_disponibilidad` e invoca la herramienta con los parámetros correspondientes. La fecha debe enviarse en formato `YYYY-MM-DD`.

### 1.4 Flujo de agendamiento

Cliente: solicita agendar una cita proporcionando los datos necesarios.

Resultado esperado: el agente recopila la información y pide una confirmación explícita antes de ejecutar `agendar_cita`. La herramienta solo debe ejecutarse después de que el cliente confirme.

### 1.5 Validación de reglas de negocio

Cliente: `quiero agendar cardiologia`

Resultado esperado: el agente rechaza amablemente la solicitud e indica las cinco especialidades disponibles, sin mencionar cardiología de nuevo ni ninguna otra especialidad inexistente como ejemplo. No debe intentar ejecutar la herramienta con una especialidad que no esté permitida.

## 2. Matriz de resolución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| Herramienta en estado rojo (`Insufficient`) en el AI Agent | Falta asignar permisos en el perfil de seguridad | Ve a Security Profiles → Flow Modules y asigna Access sobre la herramienta. Si persiste, recarga la página (Ctrl+F5) o quita y vuelve a agregar la herramienta. |
| El agente responde pero nunca invoca la herramienta | La descripción del módulo es ambigua o faltan campos en el Input Schema | Revisa la descripción, los parámetros y los tipos definidos en el Flow Module. |
| El agente responde "No atendemos esa especialidad" incluso para una válida | La tabla `citas-medicas-especialidades` está vacía o las especialidades están escritas distinto | Carga las especialidades como se indica en [tablas-dynamodb.md](tablas-dynamodb.md) y revisa que coincidan exactamente. |
| La Lambda ignora la acción enviada en el evento | Los cambios del código no se desplegaron | Pega el código actualizado en la función y pulsa Deploy. |
| El agente no recibe resultados de la Lambda | La función no tiene permiso de invocación o el ARN configurado en la herramienta es incorrecto | Revisa el ARN en el Flow Module y los permisos de invocación de la Lambda. |

## 3. Alcance y limitaciones conocidas

### 3.1 Condición de carrera al agendar (ambas versiones)

La validación de disponibilidad y la reserva se hacen en dos operaciones independientes. Solicitudes simultáneas para el mismo horario podrían generar un sobreagendamiento.

Pendiente: usar expresiones de condición (`ConditionExpression`) en las escrituras de DynamoDB.

### 3.2 Rango de códigos de cita

Los códigos se generan en el rango `CITA-9000` a `CITA-9999` (1,000 combinaciones). La versión con agente reintenta hasta cinco veces si el código ya existe; la versión con Lex no comprueba si existe. Es suficiente para un prototipo; para producción conviene una estrategia más robusta.

### 3.3 Datos personales en los logs (versión con agente)

La Lambda del agente registra el evento de entrada completo en CloudWatch Logs, lo que puede incluir el documento del paciente.

Pendiente antes de producción: enmascarar datos personales en los logs, revisar la retención en CloudWatch y aplicar controles de acceso.

### 3.4 Normalización de fecha y hora (versión con agente)

La Lambda del agente solo normaliza la especialidad (minúsculas y sin tildes). La conversión de fecha y hora depende de que el modelo respete el formato indicado en el prompt y en la descripción de la herramienta. No hay una capa de respaldo en el backend.

Pendiente: validar y normalizar fecha y hora de forma determinística en la Lambda.

### 3.5 Comportamiento del bot con intents

El bot de Lex pregunta cada dato con su frase fija y no interpreta lenguaje libre como el agente. Si la respuesta no encaja con el dato que espera, repite la pregunta según los reintentos configurados en cada slot, y la conversación puede terminar sin completar la cita. Es un comportamiento de esta configuración, no una limitación general de Lex.

### 3.6 Documento de identidad

No se valida el formato ni la longitud del documento en ninguna de las dos versiones.

## 4. Recomendaciones antes de un despliegue productivo

1. Evitar condiciones de carrera con escrituras condicionales en DynamoDB.
2. Usar una estrategia más robusta para generar códigos de cita.
3. Enmascarar o eliminar datos personales de los logs.
4. Validar fecha, hora y documento directamente en el backend.
5. Revisar los permisos IAM siguiendo el principio de mínimo privilegio.
6. Configurar la retención y el acceso a CloudWatch Logs.
7. Agregar pruebas automatizadas, incluidas las de concurrencia y casos de error.

## 5. Orden de diagnóstico

Ante un problema, revisa los componentes en este orden, que sigue el camino real de la conversación, de afuera hacia adentro:

```text
Amazon Connect (Contact Flow)
      │
      ▼
Bot puente de Lex V2
      │  (solo reenvía; revisa el switch "AI agent intent" si no lo hace)
      ▼
AI Agent
      │
      ├── ¿Herramienta disponible?
      │       └── Revisar el Security Profile
      ▼
Flow Module (la herramienta)
      │
      ├── ¿Schema correcto?
      ├── ¿Descripción correcta?
      └── ¿Lambda configurada?
      ▼
AWS Lambda
      │
      ├── ¿Código actualizado y desplegado?
      └── ¿Parámetros recibidos? (CloudWatch: "EVENTO RECIBIDO")
      ▼
DynamoDB
      │
      ├── ¿Las tablas existen?
      ├── ¿Están cargadas las especialidades?
      └── ¿La operación es correcta?
```

Este orden permite aislar rápido si el problema está en Connect, el bot puente, el AI Agent, el Flow Module, la Lambda o DynamoDB.