import time
import uuid
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

app = FastAPI()

# 1. Configuration Values
ASSIGNED_CORS_ORIGIN = "https://app-ktutgd.example.com"
RATE_LIMIT_BUCKET = 8  # 8 requests per 10 seconds

# In-memory store for rate limiting
RATE_LIMIT_STORE = {}


# Helper to check if an origin is allowed (Assigned origin OR the exam/verification page)
def is_origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    origin_lower = origin.lower()
    
    # A. Allow our assigned CORS origin
    if origin_lower == ASSIGNED_CORS_ORIGIN.lower():
        return True
        
    # B. Allow the exam page origin (covers IITM portal, local file, Live Server, codespaces, Netlify, Vercel)
    allowed_keywords = [
        "iitm.ac.in", "iitm", "github.io", "localhost", "127.0.0.1", 
        "null", "netlify", "vercel", "githubpreview.dev", "gitpod.io"
    ]
    if any(keyword in origin_lower for keyword in allowed_keywords):
        return True
        
    return False


# 2. Composed Middleware Stack
@app.middleware("http")
async def middleware_stack(request: Request, call_next):
    # 🔴 Print logs to Render console for debugging
    origin = request.headers.get("origin")
    print(f"LOG: {request.method} {request.url.path} | Origin: {origin} | Client: {request.headers.get('X-Client-Id')}")

    # --- LAYER 1: Request Context (Start) ---
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    # --- LAYER 2: CORS Preflight (OPTIONS Check) ---
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        if is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-ID, X-Client-Id"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # --- LAYER 3: Rate Limiting ---
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        now = time.time()
        
        if client_id not in RATE_LIMIT_STORE:
            RATE_LIMIT_STORE[client_id] = []
            
        RATE_LIMIT_STORE[client_id] = [t for t in RATE_LIMIT_STORE[client_id] if now - t <= 10]
        
        # If rate limit exceeded (B = 8 requests)
        if len(RATE_LIMIT_STORE[client_id]) >= RATE_LIMIT_BUCKET:
            response = JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests. Rate limit exceeded."}
            )
            if is_origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
                
            response.headers["X-Request-ID"] = request_id
            return response
            
        RATE_LIMIT_STORE[client_id].append(now)

    # --- Process the Request ---
    response = await call_next(request)

    # --- CORS & Request Context (End) ---
    response.headers["X-Request-ID"] = request_id
    if is_origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"

    return response


# 3. GET /ping Endpoint
@app.get("/ping")
def ping(request: Request):
    return {
        "email": "24f2006706@ds.study.iitm.ac.in",
        "request_id": request.state.request_id
    }