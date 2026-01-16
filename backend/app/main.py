from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router as api_router

app = FastAPI(
    title="PA Form Processing API",
    description="API for processing Prior Authorization forms",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

@app.get("/")
async def root():
    """Root endpoint returning API status"""
    return {"status": "online", "service": "PA Form Processing API"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": app.version,
        "service": app.title
    } 