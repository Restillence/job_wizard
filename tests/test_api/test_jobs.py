from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_discover_jobs():
    response = client.post(
        "/api/v1/jobs/discover",
        json={"query": "Find AI engineering roles in Berlin"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job discovery triggered"
    assert data["query"] == "Find AI engineering roles in Berlin"
