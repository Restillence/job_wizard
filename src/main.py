from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import resumes, jobs, applications, companies, pipeline, users

app = FastAPI(title="JobWiz API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resumes.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(applications.router, prefix="/api/v1")
app.include_router(companies.router, prefix="/api/v1")
app.include_router(pipeline.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
