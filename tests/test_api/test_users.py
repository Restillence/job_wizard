import uuid
from unittest.mock import patch
from tests.conftest import TestingSessionLocal
from src.models import UserSearch, User
from src.services.job_discovery import CompanySearchResult


JWT_USER_ID = "test_user_id"


def get_or_create_test_user(db, user_id=JWT_USER_ID):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user
    user = User(
        id=user_id,
        email=f"{user_id}@test.com",
        hashed_password="hashed",
    )
    db.add(user)
    db.commit()
    return user


def test_get_user_searches_empty(client):
    db = TestingSessionLocal()
    user = get_or_create_test_user(db, JWT_USER_ID)
    user_id = user.id
    db.query(UserSearch).filter(UserSearch.user_id == user_id).delete()
    db.commit()
    db.close()

    response = client.get(f"/api/v1/users/{user_id}/searches")

    assert response.status_code == 200
    data = response.json()
    assert data == []


def test_get_user_searches_with_searches(client):
    db = TestingSessionLocal()
    user = get_or_create_test_user(db, JWT_USER_ID)
    user_id = user.id

    db.query(UserSearch).filter(UserSearch.user_id == user_id).delete()

    search1 = UserSearch(
        id=str(uuid.uuid4()),
        user_id=user_id,
        cities=["Berlin"],
        industries=["AI"],
        keywords=["Python"],
        company_size="startup",
    )
    db.add(search1)

    search2 = UserSearch(
        id=str(uuid.uuid4()),
        user_id=user_id,
        cities=["Munich"],
        industries=["FinTech"],
        keywords=["Java"],
        company_size="enterprise",
    )
    db.add(search2)
    db.commit()

    response = client.get(f"/api/v1/users/{user_id}/searches")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    db.close()


def test_get_user_searches_unauthorized(client):
    db = TestingSessionLocal()
    get_or_create_test_user(db, JWT_USER_ID)
    other_user_id = "other_user_123"
    other_user = User(
        id=other_user_id,
        email="other@test.com",
        hashed_password="hashed",
    )
    db.add(other_user)
    db.commit()
    db.close()

    response = client.get(f"/api/v1/users/{other_user_id}/searches")

    assert response.status_code == 403


def test_reuse_search(client):
    db = TestingSessionLocal()
    user = get_or_create_test_user(db, JWT_USER_ID)
    user_id = user.id

    search = UserSearch(
        id=str(uuid.uuid4()),
        user_id=user_id,
        cities=["Berlin"],
        industries=["Tech"],
        keywords=["Python"],
        company_size="startup",
    )
    db.add(search)
    db.commit()
    search_id = search.id
    db.close()

    with patch(
        "src.api.routers.users.discovery_service.search_companies"
    ) as mock_search:
        mock_search.return_value = CompanySearchResult(
            companies=[
                {
                    "id": "1",
                    "name": "Test Corp",
                    "url": "https://testcorp.com/careers",
                    "url_verified": True,
                }
            ],
            total_found=1,
            newly_added=0,
            source="local",
        )

        response = client.post(f"/api/v1/users/{user_id}/searches/{search_id}/reuse")

    assert response.status_code == 200
    data = response.json()
    assert data["search_id"] == search_id
    assert data["total_found"] == 1


def test_reuse_search_not_found(client):
    db = TestingSessionLocal()
    user = get_or_create_test_user(db, JWT_USER_ID)
    user_id = user.id
    db.close()

    fake_search_id = str(uuid.uuid4())
    response = client.post(f"/api/v1/users/{user_id}/searches/{fake_search_id}/reuse")

    assert response.status_code == 404


def test_delete_search(client):
    db = TestingSessionLocal()
    user = get_or_create_test_user(db, JWT_USER_ID)
    user_id = user.id

    search = UserSearch(
        id=str(uuid.uuid4()),
        user_id=user_id,
        cities=["Berlin"],
    )
    db.add(search)
    db.commit()
    search_id = search.id
    db.close()

    response = client.delete(f"/api/v1/users/{user_id}/searches/{search_id}")

    assert response.status_code == 200

    db = TestingSessionLocal()
    deleted = db.query(UserSearch).filter(UserSearch.id == search_id).first()
    assert deleted is None
    db.close()


def test_delete_search_unauthorized(client):
    db = TestingSessionLocal()
    get_or_create_test_user(db, JWT_USER_ID)
    other_user_id = "other_user_456"
    other_user = User(
        id=other_user_id,
        email="other456@test.com",
        hashed_password="hashed",
    )
    db.add(other_user)

    search = UserSearch(
        id=str(uuid.uuid4()),
        user_id=JWT_USER_ID,
        cities=["Berlin"],
    )
    db.add(search)
    db.commit()
    search_id = search.id
    db.close()

    response = client.delete(f"/api/v1/users/{other_user_id}/searches/{search_id}")

    assert response.status_code == 403
