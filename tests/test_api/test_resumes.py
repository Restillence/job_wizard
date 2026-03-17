import os
from unittest.mock import patch


def test_upload_resume(client):
    with open("test_resume.txt", "w") as f:
        f.write("Hello my name is John and my email is john@test.com")

    with (
        patch("src.api.routers.resumes.pii_service.strip_pii") as mock_strip,
        open("test_resume.txt", "rb") as f,
    ):
        mock_strip.return_value = (
            "Hello my name is [REDACTED] and my email is [REDACTED]"
        )

        response = client.post(
            "/api/v1/resumes/upload",
            files={"file": ("resume.txt", f, "text/plain")},
        )

    assert response.status_code == 200
    assert "file_path" in response.json()

    file_path = response.json()["file_path"]
    assert os.path.exists(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "John" not in content
        assert "john@test.com" not in content
        assert "[REDACTED]" in content

    os.remove("test_resume.txt")
    os.remove(file_path)
