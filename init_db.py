from src.database import engine, SessionLocal
from src.models import Base, User

# Create all tables
Base.metadata.create_all(bind=engine)

# Insert the required test user
db = SessionLocal()
if not db.query(User).filter(User.id == 'test_user_id').first():
    new_user = User(
        id='test_user_id', 
        email='test@example.com', 
        hashed_password='fake', 
        credits_used=0, 
        credits_limit=10, 
        is_superuser=True
    )
    db.add(new_user)
    db.commit()
    print("Test user created!")

print("Database initialized successfully!")
