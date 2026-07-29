# Weighbridge Service

Small HTTP service that reads weight from the weighbridge indicator over TCP and exposes it to Frappe.

## Files
- https://github.com/Aakvatech-Limited/av_tools/blob/main/av_tools/weigh_bridge/service/run_weighbridge_service.py
- https://github.com/Aakvatech-Limited/av_tools/blob/main/av_tools/weigh_bridge/service/requirements.txt

## Install (Windows / Linux)
From this folder:

```bash
python -m venv venv
```

Windows:
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Configure
Use the **Weighbridge Settings** DocType in Frappe and pass settings to the service via `POST /read_weight`.
You only need to set the service `PORT` if you want a custom port (default is `8000`).

## Run
```bash
python run_weighbridge_service.py
```

Service URLs:
- `GET /health`
- `GET /read_weight` (query params)
- `POST /read_weight` (JSON body)

Test:
```bash
curl http://localhost:8000/health
curl "http://localhost:8000/read_weight?mock=1"
```

POST example:
```bash
curl -X POST http://localhost:8000/read_weight \
  -H "Content-Type: application/json" \
  -d '{"device_ip":"192.168.1.50","device_port":10001,"command":"RW\r\n","timeout":5}'
```

If `/health` works but `/read_weight` fails, the service is running and the issue is the scale connection or protocol.
