from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
from .routers import auth, files


# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="Storage API Zero-Trust",
    description="API de transfert sécurisé avec OTP et streaming vers MinIO",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(files.router)


# Middleware pour logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logging.info(
        f"{request.method} {request.url.path} "
        f"{response.status_code} - {process_time:.3f}s"
    )
    
    return response


@app.get("/")
async def root():
    return {
        "message": "Storage API Zero-Trust",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}