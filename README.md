# SilentPulse — AI-Powered Crisis Alert & Mapping System

A disguised personal safety app for victims of domestic violence. Sends silent SOS alerts with GPS and photo to an Azure AI Agent that maps, assesses, and coordinates emergency response.

## Architecture

```
Android App (Flutter)
    ↓ Triple-tap SOS
Captures: GPS + Photo
    ↓ HTTP POST
Azure Logic Apps (Webhook receiver)
    ↓
Azure Function (AI Agent)
    ├── Azure Maps → Reverse geocode address
    ├── Azure OpenAI → Assess severity + draft response
    └── Azure Table Storage → Store alert
    ↓
Live Dashboard (Azure Static Web Apps)
    └── Azure Maps satellite view with live alert pins
```

## Azure Services Used

- **Azure Logic Apps** — Webhook receiver and workflow orchestration
- **Azure Functions** — AI Agent (Python)
- **Azure Maps** — Satellite map + reverse geocoding
- **Azure OpenAI (GPT-4)** — Severity assessment and response guidance
- **Azure Table Storage** — Alert persistence
- **Azure Static Web Apps** — Live dashboard hosting

## Setup

### 1. Azure Function
```bash
cd azure-function
pip install -r requirements.txt
func start
```

Set environment variables:
```
AZURE_MAPS_KEY=your_key
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_KEY=your_key
AZURE_STORAGE_CONNECTION_STRING=your_connection_string
```

### 2. Logic App
Import `logic-app/workflow.json` into Azure Logic Apps via Azure Portal.

### 3. Dashboard
Update `dashboard/index.html`:
- Replace `YOUR_AZURE_MAPS_KEY`
- Replace `YOUR_AZURE_FUNCTION_URL`

Deploy to Azure Static Web Apps.

### 4. Android App
The Flutter app sends POST requests to the Logic Apps webhook URL.
Update webhook URL in `lib/services/sos_service.dart`.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/agent` | Receive SOS alert, run AI assessment |
| GET | `/api/alerts` | Return all alerts for dashboard |

## SOS Trigger
Triple-tap anywhere on the disguise screen (clock/calculator/notes) to send SOS.

## Built With
Flutter · Python · Azure Logic Apps · Azure Functions · Azure Maps · Azure OpenAI · GitHub Copilot

## License
MIT — LOVEUAD LTD © 2026
