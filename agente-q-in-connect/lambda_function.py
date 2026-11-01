import json, random, unicodedata, os
from datetime import datetime, timezone
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
ESPECIALIDADES_TABLE = os.environ.get(
    "ESPECIALIDADES_TABLE", "citas-medicas-especialidades"
)
CITAS_TABLE = os.environ.get("CITAS_TABLE", "citas-medicas-citas")

tabla_especialidades = dynamodb.Table(ESPECIALIDADES_TABLE)
tabla_citas = dynamodb.Table(CITAS_TABLE)


def _norm(t):
    t = str(t or "").strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t


def _get_horas_especialidad(esp):
    resp = tabla_especialidades.get_item(Key={"especialidad": esp})
    item = resp.get("Item")
    if not item:
        return None
    return list(item.get("horas_disponibles", []))


def _especialidades_validas():
    items = tabla_especialidades.scan().get("Items", [])
    return sorted(it["especialidad"] for it in items)


def _horas_ocupadas(esp, fecha):
    """Horas con una cita CONFIRMADA para esa especialidad y fecha (evita dobles reservas)."""
    key = f"{esp}#{fecha}"
    resp = tabla_citas.query(
        IndexName="especialidad-fecha-index",
        KeyConditionExpression=Key("especialidad_fecha").eq(key),
    )
    return {
        item.get("hora")
        for item in resp.get("Items", [])
        if item.get("estado") == "confirmada"
    }


def consultar_disponibilidad(p):
    esp = _norm(p.get("especialidad"))
    fecha = str(p.get("fecha", "")).strip()

    horas = _get_horas_especialidad(esp)
    if horas is None:
        return {
            "ok": False,
            "mensaje": "No atendemos esa especialidad. Tenemos: "
            + ", ".join(_especialidades_validas()),
        }
    if not fecha:
        return {"ok": False, "mensaje": "Necesito la fecha que prefieres."}

    ocupadas = _horas_ocupadas(esp, fecha)
    horas_libres = [h for h in horas if h not in ocupadas]

    if not horas_libres:
        return {
            "ok": False,
            "mensaje": f"No quedan horarios libres para {esp} el {fecha}. Prueba otra fecha.",
        }

    return {
        "ok": True,
        "especialidad": esp,
        "fecha": fecha,
        "horas_disponibles": horas_libres,
        "mensaje": f"Para {esp} el {fecha} tengo: {', '.join(horas_libres)}. Cual prefieres?",
    }


def agendar_cita(p):
    doc = str(p.get("documento", "")).strip()
    esp = _norm(p.get("especialidad"))
    fecha = str(p.get("fecha", "")).strip()
    hora = str(p.get("hora", "")).strip()
    if not (doc and esp and fecha and hora):
        return {
            "ok": False,
            "mensaje": "Necesito documento, especialidad, fecha y hora.",
        }

    horas = _get_horas_especialidad(esp)
    if horas is None:
        return {"ok": False, "mensaje": "Esa especialidad no esta disponible."}
    if hora not in horas:
        return {
            "ok": False,
            "mensaje": f"Ese horario no esta libre. Disponibles: {', '.join(horas)}.",
        }

    ocupadas = _horas_ocupadas(esp, fecha)
    if hora in ocupadas:
        libres = [h for h in horas if h not in ocupadas]
        libres_txt = ", ".join(libres) if libres else "ninguno por ahora"
        return {
            "ok": False,
            "mensaje": f"Esa hora ya fue reservada por otro paciente. Horarios libres: {libres_txt}.",
        }

    codigo = f"CITA-{random.randint(9000, 9999)}"
    for _ in range(5):
        resp = tabla_citas.query(
            IndexName="codigo-index", KeyConditionExpression=Key("codigo").eq(codigo)
        )
        if not resp.get("Items"):
            break
        codigo = f"CITA-{random.randint(9000, 9999)}"

    tabla_citas.put_item(
        Item={
            "documento": doc,
            "codigo": codigo,
            "paciente": p.get("paciente", "Paciente"),
            "especialidad": esp,
            "fecha": fecha,
            "hora": hora,
            "estado": "confirmada",
            "especialidad_fecha": f"{esp}#{fecha}",
            "creado_en": datetime.now(timezone.utc).isoformat(),
        }
    )

    return {
        "ok": True,
        "codigo": codigo,
        "mensaje": f"Listo, agende tu cita de {esp} el {fecha} a las {hora}. Codigo: {codigo}.",
    }


def consultar_cita(p):
    doc = str(p.get("documento", "")).strip()
    if not doc:
        return {"ok": False, "mensaje": "Necesito tu documento de identidad."}

    resp = tabla_citas.query(KeyConditionExpression=Key("documento").eq(doc))
    items = resp.get("Items", [])
    if not items:
        return {"ok": False, "mensaje": "No encontre citas con ese documento."}

    items.sort(key=lambda it: it.get("creado_en", ""), reverse=True)
    c = next((it for it in items if it.get("estado") == "confirmada"), items[0])

    return {
        "ok": True,
        "codigo": c["codigo"],
        "especialidad": c["especialidad"],
        "fecha": c["fecha"],
        "hora": c["hora"],
        "estado": c["estado"],
        "mensaje": f"Tienes cita de {c['especialidad']} el {c['fecha']} a las {c['hora']}, estado {c['estado']}. Codigo {c['codigo']}.",
    }


def reagendar_cita(p):
    codigo = str(p.get("codigo_cita", "")).strip().upper()
    nueva_fecha = str(p.get("fecha", "")).strip()
    nueva_hora = str(p.get("hora", "")).strip()
    if not (codigo and nueva_fecha and nueva_hora):
        return {
            "ok": False,
            "mensaje": "Necesito el codigo de la cita, la nueva fecha y la nueva hora.",
        }

    resp = tabla_citas.query(
        IndexName="codigo-index", KeyConditionExpression=Key("codigo").eq(codigo)
    )
    items = resp.get("Items", [])
    if not items:
        return {"ok": False, "mensaje": "No encontre una cita con ese codigo."}

    c = items[0]
    if c.get("estado") != "confirmada":
        return {
            "ok": False,
            "mensaje": "Esa cita ya no esta activa, no se puede reagendar.",
        }

    esp = c["especialidad"]
    horas = _get_horas_especialidad(esp)
    if horas is None or nueva_hora not in horas:
        horas_txt = ", ".join(horas) if horas else "sin horarios configurados"
        return {
            "ok": False,
            "mensaje": f"Ese horario no esta disponible para {esp}. Horarios: {horas_txt}.",
        }

    ocupadas = _horas_ocupadas(esp, nueva_fecha)
    if c.get("fecha") == nueva_fecha and c.get("hora") == nueva_hora:
        ocupadas.discard(nueva_hora)
    if nueva_hora in ocupadas:
        libres = [h for h in horas if h not in ocupadas]
        libres_txt = ", ".join(libres) if libres else "ninguno por ahora"
        return {
            "ok": False,
            "mensaje": f"Esa hora ya esta ocupada. Horarios libres: {libres_txt}.",
        }

    tabla_citas.update_item(
        Key={"documento": c["documento"], "codigo": c["codigo"]},
        UpdateExpression="SET fecha = :f, hora = :h, especialidad_fecha = :ef",
        ExpressionAttributeValues={
            ":f": nueva_fecha,
            ":h": nueva_hora,
            ":ef": f"{esp}#{nueva_fecha}",
        },
    )
    return {
        "ok": True,
        "codigo": codigo,
        "mensaje": f"Listo, reagende tu cita {codigo} de {esp} para el {nueva_fecha} a las {nueva_hora}.",
    }


def cancelar_cita(p):
    codigo = str(p.get("codigo_cita", "")).strip().upper()
    if not codigo:
        return {"ok": False, "mensaje": "Necesito el codigo de la cita."}

    resp = tabla_citas.query(
        IndexName="codigo-index", KeyConditionExpression=Key("codigo").eq(codigo)
    )
    items = resp.get("Items", [])
    if not items:
        return {"ok": False, "mensaje": "No encontre una cita con ese codigo."}

    c = items[0]
    tabla_citas.update_item(
        Key={"documento": c["documento"], "codigo": c["codigo"]},
        UpdateExpression="SET estado = :cancelada",
        ExpressionAttributeValues={":cancelada": "cancelada"},
    )
    return {
        "ok": True,
        "codigo": codigo,
        "mensaje": f"Cancele tu cita {codigo}. Puedo agendar otra si quieres.",
    }


_ACCIONES = {
    "consultar_disponibilidad": consultar_disponibilidad,
    "agendar_cita": agendar_cita,
    "consultar_cita": consultar_cita,
    "reagendar_cita": reagendar_cita,
    "cancelar_cita": cancelar_cita,
}


def _aplanar(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            out[k] = ", ".join(str(x) for x in v)
        elif v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out


def lambda_handler(event, context=None):
    event = event or {}
    params = event.get("Details", {}).get("Parameters", event)
    print("EVENTO RECIBIDO:", json.dumps(event))
    accion = params.get("action")
    fn = _ACCIONES.get(accion)
    try:
        res = (
            fn(params)
            if fn
            else {
                "ok": False,
                "mensaje": "Accion no reconocida.",
                "accion_recibida": accion,
            }
        )
    except Exception as e:
        print("ERROR:", repr(e))
        res = {
            "ok": False,
            "mensaje": "Tuve un problema interno. Intentemos de nuevo en un momento.",
        }
    resultado = _aplanar(res)
    print("RESULTADO DEVUELTO:", json.dumps(resultado))
    return resultado
