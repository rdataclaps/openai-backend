import base64
import math
import re
import uuid

import html2text
from dotenv import load_dotenv
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models import users
from models.schemas import UserTrainingDataCreateSchema

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Load the environment variables from the .env file
load_dotenv()


async def get_user_id(id, db):
    id = id
    user_obj = db.query(users.User).filter(users.User.id == id).first()
    if user_obj:
        return user_obj
    return None


async def create_train_data(db, id, source_filename, source_file_extensions, trained_data_path, user_id, chat_id,
                            file_size):
    train_data = UserTrainingDataCreateSchema(id=id, source_filename=source_filename,
                                              source_file_extensions=source_file_extensions,
                                              trained_data_path=trained_data_path, user_id=user_id, chat_id=chat_id,
                                              file_size=file_size)
    new_train_data = users.UserTrainData(**train_data.dict())
    db.add(new_train_data)
    db.commit()
    db.refresh(new_train_data)
    return new_train_data


async def generate_unique_uuid(db):
    while True:
        new_uuid = uuid.uuid4()
        existing_user = db.query(users.UserTrainData).filter_by(id=new_uuid).first()
        if not existing_user:
            return new_uuid


def save_chat_message(db: Session, **kwargs):
    """
    Save a ChatMessage object with dynamic parameters.

    Args:
        db (Session): The database session.
        **kwargs: Dynamic keyword arguments for creating the ChatMessage.

    Keyword Args:
        user_id (str): User ID associated with the message.
        chat_id (str): Chat ID associated with the message.
        message_text (str): Text of the message.
        message_type (MessageType): Type of the message (question or answer).
        context_text (str, optional): Context text for the message. Defaults to None.
    """
    # Create a new ChatMessage object with dynamic parameters
    chat_message = users.ChatMessage(**kwargs)

    # Add and commit the ChatMessage object to the database session
    db.add(chat_message)
    # db.commit()
    return chat_message


def convert_size(size_bytes):
    try:
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])
    except Exception:
        return ""


def format_page_content(raw_text):
    # Remove line breaks in the middle of sentences
    cleaned_text = re.sub(r"(\S)\s*\n\s*(?=\S)", r"\1 ", raw_text)

    # Remove excessive newlines
    cleaned_text = re.sub(r"\n+", "\n", cleaned_text)

    # Remove leading and trailing whitespaces
    cleaned_text = cleaned_text.strip()

    # Add ellipses (...) before and after the text on the same line
    formatted_text = f"...{cleaned_text}..."

    return formatted_text


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_email_subject(message):
    headers = message.get('payload', {}).get('headers', [])
    for header in headers:
        if header['name'] == 'Subject':
            return header['value']
    return 'No Subject'


def get_email_from(message):
    headers = message.get('payload', {}).get('headers', [])
    for header in headers:
        if header['name'] == 'From':
            return header['value']
    return 'No From'


def get_email_to(message):
    headers = message.get('payload', {}).get('headers', [])
    # print(headers)
    for header in headers:
        if header['name'] == 'Delivered-To':
            return header['value']
    return 'No Delivered-To'


def get_email_body(message):
    msg_parts = message.get('payload', {}).get('parts', [])
    body = ""

    for part in msg_parts:
        if 'data' in part['body']:
            raw_data = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            if 'text/html' in part['mimeType']:
                # Convert HTML to plain text
                body += html2text.html2text(raw_data)
                break
    return body


def get_email_date(message):
    headers = message.get('payload', {}).get('headers', [])
    # print(headers)
    for header in headers:
        if header['name'] == 'Date':
            return header['value']
    return 'No Delivered-To'
