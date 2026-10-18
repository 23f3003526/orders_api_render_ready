import base64
import json
import math
import threading
import time
import uuid
from collections import deque
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

TOTAL_ORDERS = 45
RATE_LIMIT = 18
WINDOW_SECONDS = 10.0

app = FastAPI(title="Orders API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

_state_lock = threading.Lock()
_idempotency: Dict[str, Dict[str, Any]] = {}
_client_requests: Dict[str, deque] = {}

@app.middleware("http")
async def per_client_rate_limit(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path != "/orders":
        return await call_next(request)

    client_id = request.headers.get("X-Client-Id", "").strip() or "anonymous"
    now = time.monotonic()

    with _state_lock:
        bucket = _client_requests.setdefault(client_id, deque())
        cutoff = now - WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = max(1, math.ceil(WINDOW_SECONDS - (now - bucket[0])))
            return Response(
                content=json.dumps({"detail": "Rate limit exceeded"}),
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)

    return await call_next(request)

def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")

def decode_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        offset = int(base64.urlsafe_b64decode(padded.encode()).decode())
        if not 0 <= offset <= TOTAL_ORDERS:
            raise ValueError
        return offset
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")

@app.get("/")
async def root():
    return {"service": "orders-api", "total_orders": TOTAL_ORDERS, "rate_limit": RATE_LIMIT}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/orders", status_code=201)
async def create_order(
    payload: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    key = idempotency_key.strip()
    with _state_lock:
        if key in _idempotency:
            return _idempotency[key]
        order = {
            "id": str(uuid.uuid4()),
            "status": "created",
            "details": payload or {},
        }
        _idempotency[key] = order
        return order

@app.get("/orders")
async def list_orders(limit: int = 10, cursor: Optional[str] = None):
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be at least 1")
    limit = min(limit, TOTAL_ORDERS)
    offset = decode_cursor(cursor) if cursor else 0
    end = min(offset + limit, TOTAL_ORDERS)
    items = [{"id": i, "status": "available"} for i in range(offset + 1, end + 1)]
    next_cursor = encode_cursor(end) if end < TOTAL_ORDERS else None
    return {"items": items, "next_cursor": next_cursor}
