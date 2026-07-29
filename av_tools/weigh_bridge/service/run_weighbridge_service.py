import os
import re
import socket
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import codecs


APP = FastAPI(title="Weighbridge Service", version="0.1.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("WEIGHBRIDGE_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

APP.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_DEVICE_IP = os.getenv("WEIGHBRIDGE_DEVICE_IP", "")
DEFAULT_DEVICE_PORT = int(os.getenv("WEIGHBRIDGE_DEVICE_PORT", "0") or 0)
DEFAULT_TIMEOUT = float(os.getenv("WEIGHBRIDGE_TIMEOUT", "5"))
DEFAULT_COMMAND = os.getenv("WEIGHBRIDGE_READ_COMMAND", "RW\r\n")


FLOAT_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


class ReadWeightRequest(BaseModel):
    device_ip: Optional[str] = None
    device_port: Optional[int] = None
    command: Optional[str] = None
    timeout: Optional[float] = None
    mock: Optional[int] = 0


def _read_weight_from_device(
    device_ip: str,
    device_port: int,
    command: str,
    timeout: float,
) -> str:
    if not device_ip or not device_port:
        raise ValueError("Device IP/port not configured")

    payload = _command_to_bytes(command)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect((device_ip, device_port))
        client.sendall(payload)
        data = client.recv(1024)

    return data.decode("ascii", errors="ignore").strip()


def _extract_weight(payload: str) -> float:
    match = FLOAT_PATTERN.search(payload)
    if not match:
        raise ValueError("No numeric weight found in response")
    return float(match.group(0))


def _command_to_bytes(command: str) -> bytes:
    if not command:
        return b""
    try:
        decoded = codecs.decode(command.encode("utf-8"), "unicode_escape")
        if isinstance(decoded, str):
            return decoded.encode("latin1", errors="ignore")
        return decoded
    except Exception:
        return command.encode("ascii", errors="ignore")


def _handle_read_weight(
    device_ip: Optional[str],
    device_port: Optional[int],
    command: Optional[str],
    timeout: Optional[float],
    mock: Optional[int],
):
    if mock:
        return {"weight": 0.0, "uom": "t", "raw": "MOCK"}

    cmd = command or DEFAULT_COMMAND
    to = timeout or DEFAULT_TIMEOUT

    try:
        ip = device_ip or DEFAULT_DEVICE_IP
        port = device_port or DEFAULT_DEVICE_PORT
        raw = _read_weight_from_device(ip, port, cmd, to)
        weight = _extract_weight(raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"weight": weight, "uom": "t", "raw": raw}


@APP.get("/health")
def health():
    return {"status": "ok"}


@APP.get("/read_weight")
def read_weight(
    device_ip: Optional[str] = None,
    device_port: Optional[int] = None,
    command: Optional[str] = None,
    timeout: Optional[float] = None,
    mock: Optional[int] = 0,
):
    return _handle_read_weight(
        device_ip,
        device_port,
        command,
        timeout,
        mock,
    )


@APP.post("/read_weight")
def read_weight_post(payload: ReadWeightRequest):
    return _handle_read_weight(
        payload.device_ip,
        payload.device_port,
        payload.command,
        payload.timeout,
        payload.mock,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(APP, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
