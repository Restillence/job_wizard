from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.database import get_db
from src.models import User

async def verify_jwt():
    # Mocked JWT for MVP. In production, this would validate a real JWT.
    # We return the hardcoded ID of a test user that should be created in the DB.
    return {"user_id": "test_user_id"} 

async def check_rate_limit(
    user_info: dict = Depends(verify_jwt),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_info["user_id"]).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Superuser bypass
    if user.is_superuser:
        return True
    
    # Quota check
    if user.credits_used >= user.credits_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quota exceeded. Please upgrade your subscription."
        )
    return True
