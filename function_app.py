import azure.functions as func
import logging
import json
import os
import requests

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

AZURE_MAPS_KEY = os.environ.get("AZURE_MAPS_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ALERT_EMAIL    = os.environ.get("ALERT_EMAIL", "webtestkan@gmail.com")


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


def send_alert_email(name, phone, address, lat, lng, maps_url, timestamp):
    try:
        if not RESEND_API_KEY:
            logging.warning("No Resend key")
            return
        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={
                "from": "SilentPulse <onboarding@resend.dev>",
                "to": [ALERT_EMAIL],
                "subject": f"SOS ALERT - {name}",
                "html": f"<h2>SilentPulse SOS Alert</h2><p><b>Name:</b> {name}</p><p><b>Phone:</b> {phone}</p><p><b>Address:</b> {address}</p><p><b>Coordinates:</b> {lat}, {lng}</p><p><b>Time:</b> {timestamp}</p><p><b>Map:</b> <a href='{maps_url}'>{maps_url}</a></p>"
            },
            timeout=10
        )
        logging.info("Email sent")
    except Exception as e:
        logging.error(f"Email failed: {e}")


@app.route(route="agent", methods=["POST"])
def agent(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("agent triggered")
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

    address = reverse_geocode(lat, lng)
    send_alert_email(name, phone, address, lat, lng, maps_url, timestamp)

    return func.HttpResponse(
        json.dumps({"status": "processed", "name": name, "address": address}),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="alerts", methods=["GET"])
def alerts(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"alerts": [], "status": "ok"}),
        mimetype="application/json",
        status_code=200
    )
