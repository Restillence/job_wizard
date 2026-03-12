import uuid
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_draft_application():
    job_id = str(uuid.uuid4())
    response = client.post(
        "/api/v1/applications/draft",
        params={"job_id": job_id}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Draft created"
    assert "application_id" in data

def test_approve_application():
    app_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/applications/{app_id}/approve"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == f"Application {app_id} approved"
