from fastapi import FastAPI
from src.api.routers import resumes, jobs, applications

app = FastAPI(title="JobWiz API", version="0.1.0")

app.include_router(resumes.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(applications.router, prefix="/api/v1")

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
