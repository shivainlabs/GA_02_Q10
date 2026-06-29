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
        
    # B. Allow the exam page origin (covers IITM portal, CodeTantra, workers.dev, local files)
    allowed_keywords = [
        "iitm.ac.in", "iitm", "github.io", "localhost", "127.0.0.1", 
        "null", "netlify", "vercel", "githubpreview.dev", "gitpod.io",
        "codetantra.com", "codetantra", "swayam", "nptel",
        "workers.dev"  # Added this domain
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
        response.headers["X-Request-ID"] = request_id
        if is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            
            # Echo back whatever headers the browser requested
            req_headers = request.headers.get("Access-Control-Request-Headers")
            response.headers["Access-Control-Allow-Headers"] = req_headers if req_headers else "Content-Type, X-Request-ID, X-Client-Id"
            
            # Echo back the requested method
            req_method = request.headers.get("Access-Control-Request-Method")
            response.headers["Access-Control-Allow-Methods"] = req_method if req_method else "GET, OPTIONS"
            
            if origin != "null":
                response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    # --- LAYER 3: Rate Limiting ---
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        now = time.time()
        
        # Initialize client bucket
        if client_id not in RATE_LIMIT_STORE:
            RATE_LIMIT_STORE[client_id] = []
            
        # Keep only request timestamps in the last 10 seconds
        RATE_LIMIT_STORE[client_id] = [t for t in RATE_LIMIT_STORE[client_id] if now - t <= 10]
        
        # If rate limit exceeded (B = 8 requests)
        if len(RATE_LIMIT_STORE[client_id]) >= RATE_LIMIT_BUCKET:
            # Return HTTP 429
            response = JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests. Rate limit exceeded."}
            )
            
            # Attach CORS headers to the 429 response so the browser doesn't block it
            if is_origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
                if origin != "null":
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                
            response.headers["X-Request-ID"] = request_id
            return response
            
        # Record this request timestamp
        RATE_LIMIT_STORE[client_id].append(now)

    # --- Process the Request ---
    response = await call_next(request)

    # --- CORS & Request Context (End) ---
    # Always set the X-Request-ID header on the response
    response.headers["X-Request-ID"] = request_id
    
    # Attach CORS header if the origin is allowed
    if is_origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
        if origin != "null":
            response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


# 3. GET /ping Endpoint
@app.get("/ping")
def ping(request: Request):
    return {
        "email": "24f2006706@ds.study.iitm.ac.in",  # Your registered email
        "request_id": request.state.request_id
    }