from src.database import engine, SessionLocal, enable_pg_trgm
from src.models import Base, User, Company, CompanySize

enable_pg_trgm()

Base.metadata.create_all(bind=engine)

db = SessionLocal()

if not db.query(User).filter(User.id == "test_user_id").first():
    new_user = User(
        id="test_user_id",
        email="test@example.com",
        hashed_password="fake",
        credits_used=0,
        credits_limit=10,
        is_superuser=True,
        zusatz_infos={
            "skills": ["Python", "FastAPI", "SQL", "Docker"],
            "interests": ["AI", "Startups", "FinTech"],
        },
    )
    db.add(new_user)
    db.commit()
    print("Test user created!")

test_companies = [
    {
        "id": "test_company_1",
        "name": "TechStart Berlin",
        "city": "Berlin",
        "industry": "Software",
        "company_size": CompanySize.startup,
        "url": "https://techstart-berlin.example.com/careers",
    },
    {
        "id": "test_company_2",
        "name": "Hidden Gem Munich",
        "city": "Munich",
        "industry": "AI",
        "company_size": CompanySize.hidden_champion,
        "url": "https://hidden-gem-munich.example.com/jobs",
    },
    {
        "id": "test_company_3",
        "name": "Enterprise Corp",
        "city": "Frankfurt",
        "industry": "Finance",
        "company_size": CompanySize.enterprise,
        "url": "https://enterprise-corp.example.com/careers",
    },
]

for company_data in test_companies:
    if not db.query(Company).filter(Company.id == company_data["id"]).first():
        company = Company(**company_data)
        db.add(company)
        print(f"Test company '{company_data['name']}' created!")

db.commit()
db.close()

print("Database initialized successfully!")
