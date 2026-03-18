import os
from unittest.mock import patch, MagicMock


def test_upload_resume(client):
    """Test resume upload with realistic data scientist CV."""
    
    # Create a realistic data scientist resume
    resume_content = """
JOHN SMITH
DATA SCIENTIST
Email: john.smith@email.com
LinkedIn: linkedin.com/in/johnsmith
Phone: +49-123-4567890

PROFESSIONAL SUMMARY
Senior Data Scientist with 5+ years of experience in machine learning, statistical analysis, and data visualization. Expert in Python, TensorFlow, and cloud platforms (AWS, GCP). Passionate about transforming complex datasets into actionable insights.

EXPERIENCE
Senior Data Scientist | TechCorp GmbH | Berlin | 2021 - Present
• Developed ML models for customer churn prediction (95% accuracy)
• Built real-time recommendation system serving 1M+ users
• Led data engineering team of 4 data scientists

Data Scientist | Analytics Startup | Berlin | 2019 - 2021
• Created NLP pipeline for sentiment analysis on social media data
• Developed A/B testing framework increasing conversion by 23%

EDUCATION
M.Sc. Computer Science | Technical University Berlin | 2019
B.Sc. Mathematics | University of Munich | 2017

SKILLS
Python, TensorFlow, PyTorch, Scikit-learn, SQL, Spark, AWS SageMaker, GCP Vertex AI, Docker, Kubernetes

LANGUAGES
English (Fluent), German (Native)
"""

    # Write resume to temp file
    with open("test_resume_data_scientist.txt", "w") as f:
        f.write(resume_content)

    with (
        patch("src.api.routers.resumes.pii_service.strip_pii") as mock_strip,
        patch("src.api.routers.resumes.generate_embedding") as mock_embedding,
        open("test_resume_data_scientist.txt", "rb") as f,
    ):
        # Mock PII stripping - return properly redacted content
        mock_strip.return_value = """
[REDACTED]
[REDACTED]
Email: [REDACTED]
LinkedIn: [REDACTED]
Phone: [REDACTED]

PROFESSIONAL SUMMARY
Senior Data Scientist with 5+ years of experience in machine learning, statistical analysis, and data visualization. Expert in Python, TensorFlow, and cloud platforms (AWS, GCP). Passionate about transforming complex datasets into actionable insights.

EXPERIENCE
Senior Data Scientist | [REDACTED] | Berlin | 2021 - Present
• Developed ML models for customer churn prediction (95% accuracy)
• Built real-time recommendation system serving 1M+ users
• Led data engineering team of 4 data scientists

Data Scientist | [REDACTED] | Berlin | 2019 - 2021
• Created NLP pipeline for sentiment analysis on social media data
• Developed A/B testing framework increasing conversion by 23%

EDUCATION
M.Sc. Computer Science | Technical University Berlin | 2019
B.Sc. Mathematics | University of Munich | 2017

SKILLS
Python, TensorFlow, PyTorch, Scikit-learn, SQL, Spark, AWS SageMaker, GCP Vertex AI, Docker, Kubernetes

LANGUAGES
English (Fluent), German (Native)
"""

        # Mock embedding generation
        mock_embedding.return_value = [0.1] * 3072  # 3072-dimensional embedding

        response = client.post(
            "/api/v1/resumes/upload",
            files={"file": ("resume_data_scientist.txt", f, "text/plain")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "file_path" in data

    file_path = data["file_path"]
    assert os.path.exists(file_path)

    # Verify file was saved correctly
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        # PII should be stripped
        assert "John Smith" not in content
        assert "john.smith@email.com" not in content
        assert "[REDACTED]" in content

    # Cleanup
    os.remove("test_resume_data_scientist.txt")
    os.remove(file_path)
