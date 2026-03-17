import os


def test_upload_resume(client):
    # Create a dummy file
    with open("test_resume.txt", "w") as f:
        f.write("Hello my name is John and my email is john@test.com")

    with open("test_resume.txt", "rb") as f:
        response = client.post(
            "/api/v1/resumes/upload", files={"file": ("resume.txt", f, "text/plain")}
        )

    assert response.status_code == 200
    assert "file_path" in response.json()

    # Check if saved file exists and content is redacted
    file_path = response.json()["file_path"]
    assert os.path.exists(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        # The PII Stripping Service mock or actual integration should replace PII
        # Since we are using the real service, we check for redaction.
        assert "John" not in content
        assert "john@test.com" not in content
        assert "[REDACTED]" in content

    # Cleanup
    os.remove("test_resume.txt")
    os.remove(file_path)
