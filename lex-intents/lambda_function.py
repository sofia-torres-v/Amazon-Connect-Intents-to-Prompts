import json
import re
import random
import os
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

MAX_REINTENTOS = 1  # veces que se vuelve a pedir un slot tras una validación fallida


# ---------- Helpers ----------


def _limpio(v):
    return str(v or "").strip()


def _codigo_valido(v):
    """Formato CITA-1234 (acepta minúsculas y espacios alrededor)."""
    v = _limpio(v).upper()
    return v if re.fullmatch(r"CITA-\d{4}", v) else None


def _get_horas_especialidad(esp):
    item = tabla_especialidades.get_item(Key={"especialidad": esp}).get("Item")
    return list(item.get("horas_disponibles", [])) if item else None


def _horas_ocupadas(esp, fecha):
    resp = tabla_citas.query(
        IndexName="especialidad-fecha-index",
        KeyConditionExpression=Key("especialidad_fecha").eq(f"{esp}#{fecha}"),
    )
    return {
        i.get("hora") for i in resp.get("Items", []) if i.get("estado") == "confirmada"
    }


# ---------- Acciones ----------


def consultar_disponibilidad(p):
    esp = _limpio(p.get("especialidad")).lower()
    fecha = _limpio(p.get("fecha"))

    if not (esp and fecha):
        return {"ok": False, "mensaje": "Faltan datos: especialidad y fecha."}

    horas = _get_horas_especialidad(esp)
    if horas is None:
        return {
            "ok": False,
            "reelicit": "especialidad",
            "mensaje": "Especialidad no disponible.",
        }

    ocupadas = _horas_ocupadas(esp, fecha)
    libres = [h for h in horas if h not in ocupadas]
    if not libres:
        return {
            "ok": False,
            "mensaje": f"No hay horarios disponibles para {esp} el {fecha}.",
        }
    return {
        "ok": True,
        "mensaje": f"Horarios disponibles para {esp} el {fecha}: {', '.join(libres)}.",
    }


def agendar_cita(p):
    doc = _limpio(p.get("documento"))
    esp = _limpio(p.get("especialidad")).lower()
    fecha = _limpio(p.get("fecha"))
    hora = _limpio(p.get("hora"))

    if not (doc and esp and fecha and hora):
        return {"ok": False, "mensaje": "Faltan datos para agendar."}

    horas = _get_horas_especialidad(esp)
    if horas is None:
        return {
            "ok": False,
            "reelicit": "especialidad",
            "mensaje": "Especialidad no disponible.",
        }
    if hora not in horas:
        return {
            "ok": False,
            "reelicit": "hora",
            "mensaje": f"Ese horario no existe. Horarios: {', '.join(horas)}.",
        }

    ocupadas = _horas_ocupadas(esp, fecha)
    if hora in ocupadas:
        libres = [h for h in horas if h not in ocupadas]
        return {
            "ok": False,
            "reelicit": "hora",
            "mensaje": f"Horario no disponible. Libres: {', '.join(libres) or 'ninguno'}.",
        }

    codigo = f"CITA-{random.randint(9000, 9999)}"
    tabla_citas.put_item(
        Item={
            "documento": doc,
            "codigo": codigo,
            "paciente": _limpio(p.get("paciente")) or "Paciente",
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
        "mensaje": f"Cita agendada de {esp} el {fecha} a las {hora}. Código: {codigo}.",
    }


def consultar_cita(p):
    doc = _limpio(p.get("documento"))
    if not doc:
        return {"ok": False, "mensaje": "Falta el documento."}

    items = tabla_citas.query(KeyConditionExpression=Key("documento").eq(doc)).get(
        "Items", []
    )
    if not items:
        return {"ok": False, "mensaje": "No hay citas para ese documento."}

    c = items[0]
    return {
        "ok": True,
        "mensaje": f"Cita {c['codigo']}: {c['especialidad']}, {c['fecha']} {c['hora']} ({c['estado']}).",
    }


def cancelar_cita(p):
    codigo = _codigo_valido(p.get("codigo_cita"))
    if not codigo:
        return {
            "ok": False,
            "reelicit": "codigo_cita",
            "mensaje": "Código inválido. Usa el formato CITA-1234.",
        }

    items = tabla_citas.query(
        IndexName="codigo-index", KeyConditionExpression=Key("codigo").eq(codigo)
    ).get("Items", [])
    if not items:
        return {"ok": False, "mensaje": "Cita no encontrada."}

    c = items[0]
    if c.get("estado") != "confirmada":
        return {"ok": False, "mensaje": "La cita no se puede cancelar."}

    tabla_citas.update_item(
        Key={"documento": c["documento"], "codigo": c["codigo"]},
        UpdateExpression="SET estado = :e",
        ExpressionAttributeValues={":e": "cancelada"},
    )
    return {"ok": True, "mensaje": f"Cita {codigo} cancelada."}


def reagendar_cita(p):
    codigo = _codigo_valido(p.get("codigo_cita"))
    fecha = _limpio(p.get("fecha"))
    hora = _limpio(p.get("hora"))

    if not codigo:
        return {
            "ok": False,
            "reelicit": "codigo_cita",
            "mensaje": "Código inválido. Usa el formato CITA-1234.",
        }
    if not (fecha and hora):
        return {"ok": False, "mensaje": "Faltan la fecha o la hora."}

    items = tabla_citas.query(
        IndexName="codigo-index", KeyConditionExpression=Key("codigo").eq(codigo)
    ).get("Items", [])
    if not items:
        return {"ok": False, "mensaje": "Cita no encontrada."}

    c = items[0]
    if c.get("estado") != "confirmada":
        return {"ok": False, "mensaje": "La cita no está activa."}

    esp = c["especialidad"]
    horas = _get_horas_especialidad(esp) or []
    ocupadas = _horas_ocupadas(esp, fecha)
    if hora not in horas or hora in ocupadas:
        libres = [h for h in horas if h not in ocupadas]
        return {
            "ok": False,
            "reelicit": "hora",
            "mensaje": f"Horario no disponible. Libres: {', '.join(libres) or 'ninguno'}.",
        }

    tabla_citas.update_item(
        Key={"documento": c["documento"], "codigo": c["codigo"]},
        UpdateExpression="SET fecha = :f, hora = :h, especialidad_fecha = :ef",
        ExpressionAttributeValues={":f": fecha, ":h": hora, ":ef": f"{esp}#{fecha}"},
    )
    return {
        "ok": True,
        "mensaje": f"Cita {codigo} reagendada para el {fecha} a las {hora}.",
    }


# ---------- Lex ----------


def _extraer_parametros_lex(event):
    intent = (event.get("sessionState") or {}).get("intent") or {}
    params = {}
    for name, slot in (intent.get("slots") or {}).items():
        if slot and isinstance(slot, dict) and slot.get("value"):
            v = slot["value"]
            # interpretedValue = valor ya resuelto por Lex (aplica sinónimos)
            params[name] = v.get("interpretedValue") or v.get("originalValue", "")
        else:
            params[name] = None
    return intent.get("name", ""), params


def _respuesta(event, resultado):
    ss = event.get("sessionState") or {}
    attrs = ss.get("sessionAttributes") or {}
    intent = ss.get("intent") or {"name": "", "slots": {}}
    mensaje = resultado["mensaje"]
    slot = resultado.get("reelicit")

    if not resultado["ok"] and slot:
        intentos = int(attrs.get("intentos_slot", "0") or "0") + 1
        if intentos <= MAX_REINTENTOS:
            attrs["intentos_slot"] = str(intentos)
            intent["slots"] = intent.get("slots") or {}
            intent["slots"][slot] = None
            intent["state"] = "InProgress"
            return {
                "sessionState": {
                    "dialogAction": {"type": "ElicitSlot", "slotToElicit": slot},
                    "intent": intent,
                    "sessionAttributes": attrs,
                },
                "messages": [{"contentType": "PlainText", "content": mensaje}],
            }

    attrs["intentos_slot"] = "0"
    intent["state"] = "Fulfilled"
    return {
        "sessionState": {
            "dialogAction": {"type": "Close"},
            "intent": intent,
            "sessionAttributes": attrs,
        },
        "messages": [{"contentType": "PlainText", "content": mensaje}],
    }


ACCIONES = {
    "AgendarCitaIntent": agendar_cita,
    "ConsultarCitaIntent": consultar_cita,
    "CancelarCitaIntent": cancelar_cita,
    "ConsultarDisponibilidadIntent": consultar_disponibilidad,
    "ReagendarCitaIntent": reagendar_cita,
}


def lambda_handler(event, context=None):
    intent_name, params = _extraer_parametros_lex(event)
    try:
        accion = ACCIONES.get(intent_name)
        resultado = (
            accion(params)
            if accion
            else {"ok": False, "mensaje": "No entendí tu solicitud."}
        )
    except Exception as e:
        print("ERROR:", repr(e))
        resultado = {"ok": False, "mensaje": "Ocurrió un error. Intenta de nuevo."}
    return _respuesta(event, resultado)
