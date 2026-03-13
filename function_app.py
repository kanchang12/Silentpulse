import logging
import json
import os
import requests
import azure.functions as func

app = func.FunctionApp()

AZURE_MAPS_KEY = os.environ.get("AZURE_MAPS_KEY", "")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.environ.get("AZURE_OPENAI_KEY", "")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "webtestkan@gmail.com")


def reverse_geocode(lat: str, lng: str) -> str:
    """Use Azure Maps to get address from coordinates."""
    try:
        url = f"https://atlas.microsoft.com/search/address/reverse/json"
        params = {
            "api-version": "1.0",
            "subscription-key": AZURE_MAPS_KEY,
            "query": f"{lat},{lng}"
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        address = data["addresses"][0]["address"]["freeformAddress"]
        return address
    except Exception as e:
        logging.error(f"Geocode error: {e}")
        return f"{lat}, {lng}"


def assess_severity(name: str, address: str, timestamp: str) -> dict:
    """Use Azure OpenAI Agent to assess alert and draft response."""
    try:
        headers = {
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_KEY
        }
        body = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an emergency response AI agent for SilentPulse, "
                        "a domestic violence safety platform. When you receive an SOS alert, "
                        "assess the situation and provide: "
                        "1. Severity level (HIGH/MEDIUM/LOW) "
                        "2. Recommended immediate actions for responders "
                        "3. Key information summary "
                        "Be concise and actionable."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"SOS ALERT received:\n"
                        f"Person: {name}\n"
                        f"Location: {address}\n"
                        f"Time: {timestamp}\n"
                        f"Assess this emergency and provide response guidance."
                    )
                }
            ],
            "max_tokens": 300,
            "temperature": 0.3
        }
        resp = requests.post(
            f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/gpt-4/chat/completions?api-version=2024-02-01",
            headers=headers,
            json=body,
            timeout=15
        )
        result = resp.json()
        assessment = result["choices"][0]["message"]["content"]
        return {"assessment": assessment, "status": "success"}
    except Exception as e:
        logging.error(f"AI Agent error: {e}")
        return {"assessment": "HIGH severity — immediate response required.", "status": "fallback"}


def store_alert(alert_data: dict):
    """Store alert in Azure Table Storage for dashboard."""
    try:
        from azure.data.tables import TableServiceClient
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        if not conn_str:
            return
        service = TableServiceClient.from_connection_string(conn_str)
        table = service.get_table_client("silentpulsealerts")
        table.upsert_entity({
            "PartitionKey": "alerts",
            "RowKey": alert_data["timestamp"].replace(":", "-").replace(".", "-"),
            "name": alert_data["name"],
            "phone": alert_data.get("phone", ""),
            "lat": alert_data["lat"],
            "lng": alert_data["lng"],
            "address": alert_data.get("address", ""),
            "assessment": alert_data.get("assessment", ""),
            "maps_url": alert_data.get("maps_url", ""),
            "timestamp": alert_data["timestamp"]
        })
    except Exception as e:
        logging.error(f"Storage error: {e}")


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
    timestamp = body.get("timestamp", "")

    address    = reverse_geocode(lat, lng)
    ai_result  = assess_severity(name, address, timestamp)
    assessment = ai_result["assessment"]

    alert_data = {
        "name": name, "phone": phone, "lat": lat, "lng": lng,
        "address": address, "maps_url": maps_url,
        "timestamp": timestamp, "assessment": assessment
    }
    store_alert(alert_data)

    response = {
        "status": "processed",
        "name": name,
        "address": address,
        "assessment": assessment,
        "maps_url": maps_url,
        "satellite_url": f"https://atlas.microsoft.com/map/static/png?subscription-key={AZURE_MAPS_KEY}&api-version=2022-08-01&center={lng},{lat}&zoom=16&width=800&height=600&layer=satellite&pins=default||{lng} {lat}",
        "timestamp": timestamp
    }

    logging.info(f"Alert processed: {name} at {address}")
    return func.HttpResponse(json.dumps(response), mimetype="application/json", status_code=200)


@app.route(route="alerts", methods=["GET"])
def get_alerts(req: func.HttpRequest) -> func.HttpResponse:
    """Return all alerts for dashboard."""
    try:
        from azure.data.tables import TableServiceClient
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        service = TableServiceClient.from_connection_string(conn_str)
        table = service.get_table_client("silentpulsealerts")
        alerts = [dict(e) for e in table.list_entities()]
        return func.HttpResponse(json.dumps(alerts), mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps([]), mimetype="application/json")
