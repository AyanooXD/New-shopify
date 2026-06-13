# Litestar Shopify API - Final Optimized for Railway Hobby Plan

## Plan Details (From Your Screenshot)
- $5 monthly usage credits
- Up to 8 vCPU / 8 GB RAM per replica
- Up to 5 replicas
- This configuration is optimized for the above limits

## Recommended Configuration

**Procfile (Already Set):**
```bash
web: gunicorn -k uvicorn.workers.UvicornWorker -w 8 --max-requests 1200 --max-requests-jitter 100 --timeout 300 --bind 0.0.0.0:$PORT main:app
```

### Why 8 Workers?
- Matches your 8 vCPU limit
- Good balance between performance and stability
- Each worker can handle one long-running check comfortably

## Expected Performance on Hobby Plan

| Concurrent Users | Expected Behavior          | Recommendation |
|------------------|----------------------------|----------------|
| 1 - 10           | Very Good                  | Safe           |
| 10 - 15          | Good                       | Acceptable     |
| 15 - 20          | Average (some delay)       | Monitor        |
| 20+              | Slow / Queuing             | Consider upgrade |

## How to Deploy

1. Extract this zip
2. Push all files to GitHub
3. Deploy on Railway (Hobby plan)
4. The `Procfile` will automatically use 8 workers

## Additional Tips for Best Performance

- Use **fast residential proxies** (this is the biggest factor)
- Don't run more than 15-18 concurrent checks regularly on Hobby plan
- Monitor using `/health` endpoint
- If you need more than 20 concurrent regularly, upgrade to Pro plan

## Files Included
- `main.py` → Litestar application
- `shopify_core.py` → Core engine
- `Procfile` → Pre-configured with 8 workers
- `requirements.txt`

This is the best synchronous configuration possible on Hobby plan without using background queue.
