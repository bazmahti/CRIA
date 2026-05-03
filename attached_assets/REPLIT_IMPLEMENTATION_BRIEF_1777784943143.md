# REPLIT IMPLEMENTATION BRIEF
## Unified CRIA · Ultraria Dashboard — Phase 1 Enterprise Implementation
### Author: Dr Barry Ferrier / Claude (Anthropic) — May 2026

---

## CONTEXT

This is an additive implementation on the existing CRIA Unified FastAPI project.
The existing system must not be broken. All existing routes, connectors, pipeline
logic, and protection middleware remain unchanged.

**Existing system (DO NOT MODIFY these files' core logic):**
- `main.py` (or `cria_unified.py`) — CRIA FastAPI service on port 8000
- `replit_protection.py` — IP protection middleware (already wired)
- `cria_connectors_config.py` — connector definitions
- `requirements.txt`

**API contract already in main.py (CONFIRMED, use exactly):**
- `POST /api/research/unified` → `{jobId: str, status: str}`
- `GET /api/research/unified/{jobId}` → `{jobId, query, status, startedAt, completedAt, engine: {status, result, error}}`

---

## WHAT TO IMPLEMENT — 5 STEPS IN ORDER

### STEP 1 — Add `ultraria_stub.py` to the project

Upload the provided `ultraria_stub.py` file to the project root.
Do not modify it. It is a complete FastAPI service on port 8002 with:
- `GET /health`
- `GET /api/ultraria/lanes`
- `POST /api/ultraria/run` → `{jobId, status}`
- `GET /api/ultraria/run/{jobId}` → same polling shape as CRIA

### STEP 2 — Add `unified_dashboard.html` to the project

Upload the provided `unified_dashboard.html` to the project root.
Do not modify it. The Replit agent will serve it via the route added in Step 3.

### STEP 3 — Add these three routes to `main.py`

Find the existing routes section in `main.py`. Add the following AFTER all
existing route definitions but BEFORE the `if __name__ == "__main__":` block.
Do not touch any existing routes.

```python
# ── Unified Dashboard Routes (added Phase 1) ──────────────────────────────────

import pathlib as _pathlib

@app.get("/unified", response_class=HTMLResponse)
@app.get("/unified/", response_class=HTMLResponse)
async def serve_unified_dashboard():
    """Serves the three-mode unified research dashboard."""
    html_path = _pathlib.Path(__file__).parent / "unified_dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404,
                            detail="unified_dashboard.html not found in project root")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/ultraria/proxy/health")
async def proxy_ultraria_health():
    """
    Proxies health check to Ultraria stub service (port 8002).
    Allows the dashboard to check Ultraria status via the protected CRIA origin.
    """
    import httpx
    ultraria_url = os.environ.get("ULTRARIA_URL", "http://localhost:8002")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{ultraria_url}/health")
            return r.json()
    except Exception as exc:
        return {"status": "offline", "error": str(exc),
                "service": "ultraria-stub", "phase": "1-stub"}


@app.post("/api/ultraria/proxy/run")
async def proxy_ultraria_run(request: Request):
    """
    Proxies Ultraria run requests from the dashboard to the stub service.
    Keeps the dashboard calling one origin (port 8000) for CORS simplicity.
    """
    import httpx
    ultraria_url = os.environ.get("ULTRARIA_URL", "http://localhost:8002")
    body = await request.json()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{ultraria_url}/api/ultraria/run", json=body)
            return r.json()
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"Ultraria stub unreachable: {exc}")


@app.get("/api/ultraria/proxy/run/{job_id}")
async def proxy_ultraria_poll(job_id: str):
    """Proxies Ultraria job polling from dashboard to stub service."""
    import httpx
    ultraria_url = os.environ.get("ULTRARIA_URL", "http://localhost:8002")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{ultraria_url}/api/ultraria/run/{job_id}")
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503,
                            detail=f"Ultraria stub unreachable: {exc}")
```

**Import note:** `Request` from fastapi is already imported in main.py.
`os` is already imported. `HTMLResponse` is already imported.
Only add `import pathlib as _pathlib` if pathlib is not already imported.

### STEP 4 — Update the `.replit` run command to start both services

Find the run command in `.replit` (usually `run = "python main.py"` or
`run = "uvicorn main:app --host 0.0.0.0 --port 8000"`).

Replace with a command that starts both services:

```toml
run = "bash -c 'python ultraria_stub.py & python main.py'"
```

If the existing run command uses uvicorn directly:
```toml
run = "bash -c 'python ultraria_stub.py & uvicorn main:app --host 0.0.0.0 --port 8000'"
```

The Ultraria stub reads its port from the `ULTRARIA_PORT` env var (default 8002).
No changes to port 8000.

### STEP 5 — Add one Replit Secret

In Replit → Tools → Secrets, add:

| Key | Value |
|-----|-------|
| `ULTRARIA_URL` | `http://localhost:8002` |

This tells the CRIA proxy routes where to find the Ultraria stub.
No LLM API keys are needed for Phase 1.

---

## VERIFICATION CHECKLIST

After implementation, verify all of these before closing:

```bash
# 1. Both services running
curl http://localhost:8000/health   # CRIA — expect {"status":"ok"} or similar
curl http://localhost:8002/health   # Ultraria stub — expect {"status":"ok","service":"ultraria-stub"}

# 2. Unified dashboard accessible
curl -u researcher:YOUR_PASSWORD http://localhost:8000/unified
# Expect: 200 with HTML (the unified dashboard)

# 3. Existing CRIA routes intact
curl http://localhost:8000/         # Existing CRIA dashboard — must still work
curl http://localhost:8000/connectors  # Must return connector list

# 4. Ultraria proxy working via CRIA origin
curl -u researcher:YOUR_PASSWORD http://localhost:8000/api/ultraria/proxy/health
# Expect: {"status":"ok","service":"ultraria-stub",...}

# 5. Ultraria run round-trip
curl -X POST http://localhost:8000/api/ultraria/proxy/run \
  -H "Content-Type: application/json" \
  -u researcher:YOUR_PASSWORD \
  -d '{"query":"test question","mode":"parallel","active_lanes":[1,2,3]}'
# Expect: {"jobId":"...","status":"running"}
```

---

## WHAT IS NOT IN SCOPE FOR THIS SESSION

- LLM API keys (DEEPSEEK_API_KEY, KIMI_API_KEY, GROK_API_KEY, QWEN_API_KEY,
  MISTRAL_API_KEY, OPENAI_API_KEY) — Phase 2
- Real lane calls in ultraria_stub.py — Phase 2 (stub returns realistic mock data)
- DeerFlow integration — Phase 2
- The Fibonacci task router with real tension-question generation — Phase 2

Do not attempt to implement any of these. The stub is designed to be
replaced incrementally without changing the dashboard or API contract.

---

## ARCHITECTURE NOTES FOR THE REPLIT AGENT

**Why proxy routes instead of direct cross-origin calls?**
The dashboard is served from port 8000. Direct AJAX calls to port 8002 from
the browser would require CORS configuration on every environment. The proxy
routes at `/api/ultraria/proxy/*` on port 8000 avoid this entirely — the
browser always talks to one origin, and CRIA proxies to the stub internally.

**Why not merge everything into one service?**
The separation mirrors the final architecture: CRIA will always run as its own
service; Ultraria will always run as its own service. The proxy pattern is
the permanent integration layer, not a temporary workaround.

**Password protection:**
`replit_protection.py` wraps the entire FastAPI app as middleware. All routes —
including the new `/unified` route and proxy routes — are automatically
protected by the existing password without any additional code.

**Port allocation:**
- 8000: CRIA (existing, unchanged)
- 8002: Ultraria stub (new)
- 2026: DeerFlow (Phase 2, Docker, not started in this session)

---

## FILE SUMMARY

Upload these two files to the project root before running the agent:
1. `ultraria_stub.py` — complete, do not modify
2. `unified_dashboard.html` — complete, do not modify

The agent modifies only:
1. `main.py` — adds 4 routes (Steps 3 above)
2. `.replit` — updates run command (Step 4 above)

That is the complete scope. No other files should be touched.
