

def main():
  print("Hello learners!")

if __name__=="__main__":
  main(Zammad)

  import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException
import httpx
import os
import httpx
from fastapi import FastAPI, Request, HTTPException

app = FastAPI(title="Bridge Monitoreo → Helpdesk")

# ======= CONFIG por variables de entorno =======
ZAMMAD_BASE_URL = os.getenv("ZAMMAD_BASE_URL", "https://tu-zammad.example.com")
# Nota: Zammad acepta "Authorization: Token token=XXX" y (en instalaciones recientes) "Authorization: Bearer XXX".
# Usa el que funcione en tu instancia.
ZAMMAD_TOKEN = os.getenv("ZAMMAD_TOKEN", "CAMBIA_ESTE_TOKEN")
ZAMMAD_AUTH_SCHEME = os.getenv("ZAMMAD_AUTH_SCHEME", "Token")  # "Token" o "Bearer"
ZAMMAD_GROUP = os.getenv("ZAMMAD_GROUP", "Users")  # nombre del grupo/cola destino en Zammad
ZAMMAD_PRIORITY = os.getenv("ZAMMAD_PRIORITY", "2 normal")  # o un ID/Nombre válido en tu Zammad
DEFAULT_CUSTOMER = os.getenv("DEFAULT_CUSTOMER", "guess:monitoring@local")  # usa "guess:email" para crear/relacionar cliente

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"{ZAMMAD_AUTH_SCHEME} token={ZAMMAD_TOKEN}" if ZAMMAD_AUTH_SCHEME.lower()=="token"
                     else f"{ZAMMAD_AUTH_SCHEME} {ZAMMAD_TOKEN}"
}

# ======= HELPERS =======
async def create_zammad_ticket(
    title: str,
    body: str,
    customer: Optional[str] = None,
    group: Optional[str] = None,
    priority: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Crea un ticket en Zammad.
    Ver campos en docs oficiales (title, group, customer, priority, article...). 
    """
    payload: Dict[str, Any] = {
        "title": title[:250],
        "group": group or ZAMMAD_GROUP,
        "priority": priority or ZAMMAD_PRIORITY,
        "customer_id": customer or DEFAULT_CUSTOMER,
        "article": {
            "subject": title[:250],
            "body": body,
            "type": "note",           # también "email", "web", etc. según tu flujo
            "content_type": "text/plain",
            "internal": False
        }
    }
    if tags:
        payload["tags"] = tags

    url = f"{ZAMMAD_BASE_URL.rstrip('/')}/api/v1/tickets"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, headers=HEADERS, json=payload)
        if r.status_code >= 300:
            raise HTTPException(status_code=502, detail={"error": "Zammad error", "status": r.status_code, "body": r.text})
        return r.json()

def summarize_labels(labels: Dict[str, Any]) -> str:
    kv = [f"{k}={v}" for k, v in labels.items()]
    return ", ".join(sorted(kv))

# ======= ENDPOINT: Prometheus/Grafana Alertmanager =======
@app.post("/webhooks/alertmanager")
async def from_alertmanager(req: Request):
    """
    Recibe el payload estándar de Alertmanager/Grafana Alerting y crea un ticket por cada alerta activa (firing).
    """
    data = await req.json()
    alerts: List[Dict[str, Any]] = data.get("alerts", [])
    created = []

    for a in alerts:
        status = a.get("status", "firing")
        if status != "firing":
            continue
        labels = a.get("labels", {})
        annotations = a.get("annotations", {})
        title = annotations.get("summary") or labels.get("alertname") or "Alerta de monitoreo"
        desc = annotations.get("description") or ""
        lbls = summarize_labels(labels)
        starts_at = a.get("startsAt", "")
        ends_at = a.get("endsAt", "")
        generatorURL = a.get("generatorURL", "")

        body = (
            f"{desc}\n\n"
            f"Labels: {lbls}\n"
            f"Inicia: {starts_at}\n"
            f"Generador: {generatorURL}\n"
            f"Fin (si aplica): {ends_at}"
        )

        # Construye el 'customer' si el label trae un email; si no, usa DEFAULT_CUSTOMER
        customer = None
        for key in ("owner", "email", "customer", "client_email"):
            v = labels.get(key) or annotations.get(key)
            if v and "@" in str(v):
                customer = f"guess:{v}"
                break

        ticket = await create_zammad_ticket(
            title=title,
            body=body,
            customer=customer
        )
        created.append({"id": ticket.get("id"), "number": ticket.get("number"), "title": ticket.get("title")})

    return {"created": created, "count": len(created)}

# ======= ENDPOINT: Zabbix Webhook (flexible) =======
@app.post("/webhooks/zabbix")
async def from_zabbix(req: Request):
    """
    Recibe un JSON personalizado desde Zabbix (media type Webhook). 
    Ajusta aquí los nombres de campos según tu plantilla en Zabbix.
    """
    data = await req.json()
    # Ejemplo: Zabbix te deja formatear el JSON; aquí asumimos algunos campos de ejemplo:
    title = data.get("event_name") or data.get("trigger") or "Evento Zabbix"
    severity = data.get("severity") or data.get("priority")
    host = data.get("host") or data.get("hostname")
    problem = data.get("problem") or data.get("message") or ""
    url = data.get("event_url") or data.get("zabbix_url") or ""

    body = f"Host: {host}\nSeveridad: {severity}\n\n{problem}\n\nMás info: {url}"
    customer_email = data.get("customer_email") or data.get("client_email")
    customer = f"guess:{customer_email}" if customer_email else None

    ticket = await create_zammad_ticket(
        title=title,
        body=body,
        customer=customer,
        tags=data.get("tags")
    )
    return {"id": ticket.get("id"), "number": ticket.get("number"), "title": ticket.get("title")}

import requests

def trivia_fetch(number: int):
    """Obtiene datos de trivia de numbersapi"""
    url = f"http://numbersapi.com/{number}?json"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()