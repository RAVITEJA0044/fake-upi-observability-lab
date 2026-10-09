import json
import logging
import os
import random
import time
import uuid
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Fake UPI Payment API", version="1.0.0")

LOG_FILE = Path(os.getenv("LOG_FILE", "/tmp/payment-app.log"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("fake_upi")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(LOG_FILE)
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)
logger.propagate = False

REQUESTS = Counter("payment_api_requests_total", "HTTP requests", ["method", "endpoint", "status"])
PAYMENTS = Counter("fake_upi_payments_total", "Simulated payment outcomes", ["result"])
LATENCY = Histogram("payment_api_request_duration_seconds", "Request duration", ["endpoint"],
                    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5))
IN_FLIGHT = Gauge("payment_api_in_flight_requests", "Requests currently being handled")
SCENARIO = "normal"
scenario_lock = Lock()
payments = {}

def emit_log(level, event, **fields):
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "service": "fake-upi-payment-api",
        "event": event,
        **fields,
    }
    logger.info(json.dumps(record, separators=(",", ":")))

def current_scenario():
    with scenario_lock:
        return SCENARIO

@app.middleware("http")
async def metrics_and_logging(request, call_next):
    start = time.perf_counter()
    endpoint = request.url.path
    IN_FLIGHT.inc()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception as exc:
        emit_log("ERROR", "unhandled_exception", endpoint=endpoint, error=str(exc))
        raise
    finally:
        duration = time.perf_counter() - start
        IN_FLIGHT.dec()
        REQUESTS.labels(request.method, endpoint, str(status)).inc()
        LATENCY.labels(endpoint).observe(duration)
        if endpoint not in ("/metrics", "/health"):
            emit_log("INFO" if status < 500 else "ERROR", "http_request",
                     method=request.method, endpoint=endpoint, status=status,
                     duration_ms=round(duration * 1000, 2))

@app.get("/")
def root():
    return {"service": "fake-upi-payment-api", "warning": "SIMULATION ONLY", "scenario": current_scenario()}

@app.get("/health")
def health():
    mode = current_scenario()
    if mode == "down":
        raise HTTPException(status_code=503, detail="Simulated service unavailable")
    return {"status": "UP", "scenario": mode}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/payments")
def create_payment():
    mode = current_scenario()
    if mode == "down":
        raise HTTPException(status_code=503, detail="Simulated service unavailable")
    if mode == "slow":
        time.sleep(2)
    if mode == "errors" or (mode == "random" and random.random() < 0.35):
        PAYMENTS.labels("failed").inc()
        fake_id = "pay_" + uuid.uuid4().hex[:12]
        emit_log("ERROR", "payment_failed", payment_id=fake_id, reason="SIMULATED_UPSTREAM_TIMEOUT")
        raise HTTPException(status_code=500, detail={"payment_id": fake_id, "error": "SIMULATED_UPSTREAM_TIMEOUT"})
    payment_id = "pay_" + uuid.uuid4().hex[:12]
    payments[payment_id] = {"payment_id": payment_id, "status": "SUCCESS", "amount": round(random.uniform(10, 5000), 2)}
    PAYMENTS.labels("success").inc()
    emit_log("INFO", "payment_created", payment_id=payment_id, status="SUCCESS", amount=payments[payment_id]["amount"])
    return payments[payment_id]

@app.get("/payments/{payment_id}")
def get_payment(payment_id: str):
    if current_scenario() == "slow":
        time.sleep(2)
    item = payments.get(payment_id)
    if not item:
        emit_log("WARN", "payment_not_found", payment_id=payment_id)
        raise HTTPException(status_code=404, detail="Fake payment ID not found")
    return item

@app.post("/admin/scenario/{mode}")
def set_scenario(mode: str):
    global SCENARIO
    allowed = {"normal", "errors", "slow", "down", "random"}
    if mode not in allowed:
        raise HTTPException(status_code=400, detail={"allowed_modes": sorted(allowed)})
    with scenario_lock:
        SCENARIO = mode
    emit_log("WARN", "scenario_changed", scenario=mode)
    return {"scenario": mode, "warning": "Simulation only; no real payments are processed."}

@app.get("/admin/scenario")
def get_scenario():
    return {"scenario": current_scenario(), "available": ["normal", "errors", "slow", "down", "random"]}
