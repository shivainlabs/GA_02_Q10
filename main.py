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
    
    # 1. Allow our assigned CORS origin
    if origin_lower == ASSIGNED_CORS_ORIGIN.lower():
        return True
        
    # 2. Allow the exam page origin (which is on github.io or local environment)
    if "github.io" in origin_lower or "github" in origin_lower or "localhost" in origin_lower:
        return True
        
    return False


# 2. Composed Middleware Stack
@app.middleware("http")
async def middleware_stack(request: Request, call_next):
    # --- LAYER 1: Request Context (Start) ---
    # Read client request ID or generate a fresh UUID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    # Save the request ID to the request state so the endpoint can read it
    request.state.request_id = request_id

    # --- LAYER 2: CORS Preflight (OPTIONS Check) ---
    if request.method == "OPTIONS":
        origin = request.headers.get("origin")
        if is_origin_allowed(origin):
            response = Response(status_code=200)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-ID, X-Client-Id"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        else:
            # Block origin (do not return any Access-Control-Allow-Origin header)
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

    # --- LAYER 3: Rate Limiting ---
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        now = time.time()
        
        # Initialize client bucket
        if client_id not in RATE_LIMIT_STORE:
            RATE_LIMIT_STORE[client_id] = []
            
        # Keep only request timestamps in the last 10 seconds
        RATE_LIMIT_STORE[client_id] = [t for t in RATE_LIMIT_STORE[client_id] if now - t <= 10]
        
        # If bucket limit is exceeded (B = 8 requests)
        if len(RATE_LIMIT_STORE[client_id]) >= RATE_LIMIT_BUCKET:
            # Return HTTP 429
            response = JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests. Rate limit exceeded."}
            )
            
            # Attach CORS headers to the 429 response so the browser doesn't block it
            origin = request.headers.get("origin")
            if is_origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
                
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
    origin = request.headers.get("origin")
    if is_origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"

    return response


# 3. GET /ping Endpoint
@app.get("/ping")
def ping(request: Request):
    return {
        "email": "24f2006706@ds.study.iitm.ac.in", # Your registered email
        "request_id": request.state.request_id
    }