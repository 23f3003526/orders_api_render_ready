# FastAPI Orders API

Implements idempotent `POST /orders`, cursor pagination over fixed IDs 1–45,
per-client rate limiting (18 requests per 10 seconds), and CORS.

## Render settings
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Submit the deployed base URL, such as `https://your-service.onrender.com`.

State is held in memory and resets on restart. Use one Render instance for this grader.
