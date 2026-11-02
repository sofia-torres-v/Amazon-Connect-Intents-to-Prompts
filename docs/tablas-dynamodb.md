# Tablas de DynamoDB

← [Volver al README principal](../README.md)

Las dos versiones (intents y agente) usan las mismas dos tablas, con facturación bajo demanda (_on-demand_). Los nombres se leen de las variables de entorno `ESPECIALIDADES_TABLE` y `CITAS_TABLE`; si no existen, el código usa los nombres por defecto de abajo.

---

## 1. `citas-medicas-especialidades`

Guarda las especialidades que se atienden y sus horarios.

| Elemento      | Valor                   |
| ------------- | ----------------------- |
| Partition key | `especialidad` (String) |
| Sort key      | ninguna                 |

| Atributo            | Tipo            | Descripción                                            |
| ------------------- | --------------- | ------------------------------------------------------ |
| `especialidad`      | String          | Nombre de la especialidad, en minúsculas y sin tildes  |
| `horas_disponibles` | Lista de String | Horarios que se ofrecen cada día para esa especialidad |

### Especialidades cargadas

- `medicina general`
- `pediatria`
- `odontologia`
- `dermatologia`
- `oftalmologia`

### Ejemplo de elemento

```json
{
  "especialidad": "medicina general",
  "horas_disponibles": ["08:00", "09:30", "11:00", "14:00", "16:30"]
}
```

Para ver el formato exacto que guardaste, abre la tabla en DynamoDB (**Explore items**), selecciona un elemento y cambia a la vista JSON.

> La versión con agente convierte lo que escribe el cliente a minúsculas y sin tildes antes de buscar. La versión con Lex solo lo pasa a minúsculas, así que el tipo de slot debe devolver el nombre exacto, sin tilde (por ejemplo `pediatria`).

---

## 2. `citas-medicas-citas`

Guarda las citas agendadas.

| Elemento      | Valor                |
| ------------- | -------------------- |
| Partition key | `documento` (String) |
| Sort key      | `codigo` (String)    |

| Atributo             | Tipo   | Descripción                                                  |
| -------------------- | ------ | ------------------------------------------------------------ |
| `documento`          | String | Documento de identidad del paciente                          |
| `codigo`             | String | Código de la cita, con formato `CITA-9000` a `CITA-9999`     |
| `paciente`           | String | Nombre del paciente (por defecto, `Paciente`)                |
| `especialidad`       | String | Especialidad de la cita                                      |
| `fecha`              | String | Fecha en formato `YYYY-MM-DD`                                |
| `hora`               | String | Hora de la cita, en el mismo formato que `horas_disponibles` |
| `estado`             | String | `confirmada` o `cancelada`                                   |
| `especialidad_fecha` | String | Clave compuesta `especialidad#fecha`, usada por un índice    |
| `creado_en`          | String | Fecha y hora de creación, en ISO 8601 (UTC)                  |

### Índices secundarios globales

| Índice                     | Partition key        | Proyección          | Para qué se usa                                                     |
| -------------------------- | -------------------- | ------------------- | ------------------------------------------------------------------- |
| `codigo-index`             | `codigo`             | Todos los atributos | Buscar una cita solo con su código (consultar, cancelar, reagendar) |
| `especialidad-fecha-index` | `especialidad_fecha` | Todos los atributos | Ver qué horas ya están ocupadas para una especialidad en una fecha  |

### Ejemplo de elemento (datos ficticios)

```json
{
  "documento": "12345678",
  "codigo": "CITA-9001",
  "paciente": "Paciente de prueba",
  "especialidad": "pediatria",
  "fecha": "2026-11-05",
  "hora": "10:00",
  "estado": "confirmada",
  "especialidad_fecha": "pediatria#2026-11-05",
  "creado_en": "2026-11-01T15:30:00+00:00"
}
```

---

## 3. Cómo crearlas en la consola

En DynamoDB, **Create table**:

1. `citas-medicas-especialidades`: partition key `especialidad` (String). En **Table settings**, elige **Customize settings** y capacidad **On-demand**.
2. `citas-medicas-citas`: partition key `documento` (String) y sort key `codigo` (String), también con capacidad **On-demand**.
3. En `citas-medicas-citas`, pestaña **Indexes → Create index**, crea los dos índices de la tabla anterior, con proyección **All**.

Después, carga cada especialidad con **Explore items → Create item** (vista JSON), usando el formato del ejemplo de la sección 1.

---

## 4. Permisos de la Lambda

La función necesita leer y escribir en las dos tablas, y también consultar sus índices. En IAM, el recurso de los índices termina en `/index/*`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:<REGION>:<ID_DE_CUENTA>:table/citas-medicas-especialidades",
        "arn:aws:dynamodb:<REGION>:<ID_DE_CUENTA>:table/citas-medicas-citas",
        "arn:aws:dynamodb:<REGION>:<ID_DE_CUENTA>:table/citas-medicas-citas/index/*"
      ]
    }
  ]
}
```

Sustituye los marcadores por tu región y tu ID de cuenta antes de guardarla. El permiso `dynamodb:Scan` solo lo usa la versión con agente, para listar las especialidades cuando el cliente pide una que no existe.
