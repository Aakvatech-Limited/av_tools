#!/usr/bin/env python3
import argparse
import os
import re

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

DEFAULT_UPSTREAM = os.getenv(
    "WEIGHBRIDGE_UPSTREAM_URL", "http://192.168.1.220/ValPoids.cgx"
)
DEFAULT_TIMEOUT = float(os.getenv("WEIGHBRIDGE_TIMEOUT", "5"))

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_valpoids(xml_text):
    match = re.search(r"<id>ValPoids</id><value>\s*([^<]+)</value>", xml_text)
    if not match:
        raise ValueError("ValPoids not found in response")
    raw_value = match.group(1).strip()
    number_match = re.search(r"[-+]?\d*\.?\d+", raw_value)
    if not number_match:
        raise ValueError("No numeric weight found in response")
    return float(number_match.group(0)), raw_value


def fetch_upstream(url, timeout):
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/ValPoids.cgx")
def proxy_xml():
    try:
        xml_text = fetch_upstream(app.state.upstream_url, app.state.timeout)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PlainTextResponse(xml_text, media_type="application/xml")


@app.get("/read_weight")
def read_weight():
    try:
        xml_text = fetch_upstream(app.state.upstream_url, app.state.timeout)
        weight, raw = parse_valpoids(xml_text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"weight": weight, "raw": raw, "uom": "kg"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--ssl-cert", default=os.getenv("WEIGHBRIDGE_SSL_CERT", ""))
    parser.add_argument("--ssl-key", default=os.getenv("WEIGHBRIDGE_SSL_KEY", ""))
    args = parser.parse_args()

    app.state.upstream_url = args.upstream
    app.state.timeout = args.timeout

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_certfile=args.ssl_cert or None,
        ssl_keyfile=args.ssl_key or None,
        log_level="info",
    )


if __name__ == "__main__":
    main()
