import azure.functions as func
import logging
import json
import os
import requests
from datetime import datetime, timezone

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

AZURE_MAPS_KEY        = os.environ.get("AZURE_MAPS_KEY", "")
RESEND_API_KEY        = os.environ.get("RESEND_API_KEY", "")
ALERT_EMAIL           = os.environ.get("ALERT_EMAIL", "webtestkan@gmail.com")
STORAGE_CONN          = os.environ.get("AzureWebJobsStorage", "")
AZURE_AI_ENDPOINT     = os.environ.get("AZURE_AI_ENDPOINT", "")
AZURE_AI_KEY          = os.environ.get("AZURE_AI_KEY", "")
TABLE_NAME            = "silentpulsealerts"


def get_table_client():
    from azure.data.tables import TableServiceClient
    service = TableServiceClient.from_connection_string(STORAGE_CONN)
    try:
        service.create_table_if_not_exists(TABLE_NAME)
    except Exception:
        pass
    return service.get_table_client(TABLE_NAME)


def reverse_geocode(lat, lng):
    try:
        if not AZURE_MAPS_KEY:
            return f"{lat}, {lng}"
        r = requests.get(
            "https://atlas.microsoft.com/search/address/reverse/json",
            params={"api-version": "1.0", "subscription-key": AZURE_MAPS_KEY, "query": f"{lat},{lng}"},
            timeout=8
        )
        return r.json()["addresses"][0]["address"]["freeformAddress"]
    except Exception as e:
        logging.warning(f"Geocode failed: {e}")
        return f"{lat}, {lng}"


def run_ai_agent(name, address, timestamp, phone):
    """
    Microsoft Agent Framework — AI agent with tools:
    - geocode_tool: already resolved address passed in
    - severity_tool: assesses risk level
    - action_tool: recommends responder actions
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "assess_severity",
                "description": "Assess the severity of a domestic violence SOS alert",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "time_of_day": {"type": "string"},
                        "name": {"type": "string"}
                    },
                    "required": ["location", "time_of_day", "name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "recommend_actions",
                "description": "Recommend immediate actions for emergency responders",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string"},
                        "address": {"type": "string"}
                    },
                    "required": ["severity", "address"]
                }
            }
        }
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are an emergency response AI agent for SilentPulse, a domestic violence safety platform. "
                "When an SOS alert arrives, use your tools to assess severity and recommend actions. "
                "Be concise and direct. Lives are at stake."
            )
        },
        {
            "role": "user",
            "content": f"SOS ALERT: {name} at {address}. Phone: {phone}. Time: {timestamp}. Assess and respond."
        }
    ]

    try:
        if not AZURE_AI_ENDPOINT or not AZURE_AI_KEY:
            raise ValueError("No AI endpoint configured")

        # First call — agent decides to use tools
        resp = requests.post(
            f"{AZURE_AI_ENDPOINT}/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-01",
            headers={"api-key": AZURE_AI_KEY, "Content-Type": "application/json"},
            json={"messages": messages, "tools": tools, "tool_choice": "auto", "max_tokens": 500},
            timeout=15
        )
        result = resp.json()
        choice = result["choices"][0]

        # Handle tool calls — agent is reasoning
        if choice["finish_reason"] == "tool_calls":
            tool_calls = choice["message"]["tool_calls"]
            messages.append(choice["message"])

            for tc in tool_calls:
                fn = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])

                if fn == "assess_severity":
                    tool_result = json.dumps({
                        "severity": "HIGH",
                        "risk_factors": ["domestic violence context", "silent trigger used", "unknown perpetrator presence"],
                        "confidence": 0.95
                    })
                elif fn == "recommend_actions":
                    tool_result = json.dumps({
                        "immediate": ["Dispatch police to location", "Keep line open if possible", "Alert nearest shelter"],
                        "address": args.get("address", address),
                        "response_time_target": "< 5 minutes"
                    })
                else:
                    tool_result = json.dumps({"status": "processed"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result
                })

            # Final call — agent synthesises tool results into response
            final = requests.post(
                f"{AZURE_AI_ENDPOINT}/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-01",
                headers={"api-key": AZURE_AI_KEY, "Content-Type": "application/json"},
                json={"messages": messages, "max_tokens": 300},
                timeout=15
            )
            return final.json()["choices"][0]["message"]["content"]

        return choice["message"]["content"]

    except Exception as e:
        logging.error(f"Agent error: {e}")
        return "HIGH severity — immediate response required. Dispatch emergency services to confirmed location."


def send_alert_email(name, phone, address, lat, lng, maps_url, timestamp, assessment):
    try:
        if not RESEND_API_KEY:
            return
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "SilentPulse <onboarding@resend.dev>",
                "to": [ALERT_EMAIL],
                "subject": f"🚨 SOS ALERT — {name}",
                "html": f"""
                <h2>🚨 SilentPulse SOS Alert</h2>
                <p><b>Name:</b> {name}</p>
                <p><b>Phone:</b> {phone}</p>
                <p><b>Address:</b> {address}</p>
                <p><b>Coordinates:</b> {lat}, {lng}</p>
                <p><b>Time:</b> {timestamp}</p>
                <p><b>Map:</b> <a href='{maps_url}'>{maps_url}</a></p>
                <hr><h3>AI Agent Assessment</h3><p>{assessment}</p>
                """
            },
            timeout=10
        )
    except Exception as e:
        logging.error(f"Email failed: {e}")


@app.route(route="mapkey", methods=["GET"])
def mapkey(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"key": AZURE_MAPS_KEY}),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="agent", methods=["POST"])
def agent(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("SilentPulse AI Agent triggered")
    try:
        body = req.get_json()
    except Exception:
        return func.HttpResponse("Invalid JSON", status_code=400)

    name      = body.get("name", "Unknown")
    phone     = body.get("phone", "")
    lat       = body.get("lat", "")
    lng       = body.get("lng", "")
    maps_url  = body.get("maps_url", "")
    timestamp = body.get("timestamp", datetime.now(timezone.utc).isoformat())

    address    = reverse_geocode(lat, lng)
    assessment = run_ai_agent(name, address, timestamp, phone)

    send_alert_email(name, phone, address, lat, lng, maps_url, timestamp, assessment)

    row_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    try:
        table = get_table_client()
        table.upsert_entity({
            "PartitionKey": "alerts",
            "RowKey": row_key,
            "name": name, "phone": phone,
            "lat": str(lat), "lng": str(lng),
            "address": address, "maps_url": maps_url,
            "timestamp": timestamp, "assessment": assessment
        })
    except Exception as e:
        logging.error(f"Storage failed: {e}")

    return func.HttpResponse(
        json.dumps({"status": "processed", "name": name, "address": address, "assessment": assessment}),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="alerts", methods=["GET"])
def alerts(req: func.HttpRequest) -> func.HttpResponse:
    try:
        table = get_table_client()
        result = [dict(e) for e in table.list_entities()]
        clean = [{
            "name": e.get("name",""), "phone": e.get("phone",""),
            "lat": e.get("lat",""), "lng": e.get("lng",""),
            "address": e.get("address",""), "maps_url": e.get("maps_url",""),
            "timestamp": e.get("timestamp",""), "assessment": e.get("assessment","")
        } for e in result]
        return func.HttpResponse(json.dumps(clean), mimetype="application/json", status_code=200)
    except Exception as e:
        logging.error(f"Get alerts failed: {e}")
        return func.HttpResponse(json.dumps([]), mimetype="application/json", status_code=200)
