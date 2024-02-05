from typing import Optional

from database import session
from models.users import User
from models.schemas import Register


def get_user(email: str) -> Optional[User]:
    with session() as db:
        return db.query(User).filter(User.email == email).one_or_none()


def update_access_token(email: str, access_token: str,refresh_token:str):
    with session() as db:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.access_token = access_token
            user.refresh_token = refresh_token
            db.commit()
            db.refresh(user)


def add_user(user: Register) -> Optional[User]:
    db_user = User(**user.dict())
    with session() as db:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    return db_user
