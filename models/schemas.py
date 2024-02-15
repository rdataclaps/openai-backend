import os
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr
from typing import Optional
load_dotenv()


class UserCreateBaseSchema(BaseModel):
    email: str
    name: str

    class Config:
        orm_mode = True


class UserTrainingDataCreateSchema(BaseModel):
    id: uuid.UUID
    source_filename: str
    source_file_extensions: str
    trained_data_path: str
    user_id: uuid.UUID 
    chat_id:  Optional[uuid.UUID]
    file_size: int


class User(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    email: str


class Register(BaseModel):
    password: str
    email: str


class Token(BaseModel):
    email: str
    password: str


class Login(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class Refresh(BaseModel):
    access_token: str
    token_type: str


class Settings(BaseModel):
    authjwt_secret_key: str = (
        os.getenv("authjwt_secret_key")
    )
    authjwt_access_token_expires: timedelta = timedelta(hours=1)
    authjwt_refresh_token_expires: timedelta = timedelta(days=30)
