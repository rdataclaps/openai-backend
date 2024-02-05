import uuid
from datetime import datetime
from enum import Enum as PythonEnum

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    DateTime
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import relationship

from database import Base
from utils import get_password_hash
from .model_mixin import AuditMixin


class Model(Base):
    __abstract__ = True
    __tablename__ = ""

    id = Column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )

    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: datetime = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(Model):
    __tablename__ = "users"

    password: str = Column(String(length=64), nullable=False)
    email: str = Column(String(length=64), nullable=False, unique=True, index=True)
    access_token: str = Column(String(length=2000), nullable=True, index=True)
    refresh_token: str = Column(String(length=2000), nullable=True, index=True)
    credit = Column(Float(precision=6), default=100.000000)

    def __init__(self, password: str, **kwargs):
        super(User, self).__init__(**kwargs)
        self.generate_password_hash(password)

    def generate_password_hash(self, password: str) -> None:
        self.password = get_password_hash(password)


class UserCreditHistory(Base, AuditMixin):
    __tablename__ = "usercredithistory"
    id = Column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    credit = Column(Float(precision=7))


class Chat(Base, AuditMixin):
    __tablename__ = "chats"
    id = Column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )
    title = Column(String, nullable=False)
    chat_specific = Column(Boolean, nullable=False, default=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user = relationship("User")


class MessageType(str, PythonEnum):
    QUESTION = "question"
    ANSWER = "answer"


class ChatMessage(Base, AuditMixin):
    __tablename__ = "chat_messages"

    id = Column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )
    message_text = Column(String, nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chat_id = Column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    message_type = Column(
        Enum(MessageType), nullable=False, default=MessageType.QUESTION
    )
    context_text = Column(ARRAY(String), default=None, nullable=True)
    message_metadata = Column(ARRAY(JSON), default=None, nullable=True)

    # Define relationships with User and Chat models
    user = relationship("User")
    chat = relationship("Chat")


class UserTrainData(Base, AuditMixin):
    __tablename__ = "usertraindatas"
    id = Column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )
    source_filename = Column(String(length=255))
    source_file_extensions = Column(String(length=10))
    trained_data_path = Column(String(length=255))
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chat_id = Column(
        UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=True
    )
    file_size = Column(Integer, default=0)
    user = relationship("User")


class Template(Base, AuditMixin):
    __tablename__ = "templates"

    id = Column(
        UUID(as_uuid=True), primary_key=True, nullable=False, default=uuid.uuid4
    )
    title = Column(String, nullable=False)
    questions = Column(Text, nullable=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    user = relationship("User")
