from io import BytesIO
import os

import jwt
import pdfkit
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from xhtml2pdf import pisa
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse,JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi_jwt_auth import AuthJWT
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from database import get_db
from fastapi.responses import RedirectResponse
from models.schemas import Login, Refresh, Register, Token, User
from services import add_user, get_user, update_access_token
from utils import generate_unique_uuid, get_email_body, get_email_from, get_email_subject, get_email_to, verify_password, get_email_date

load_dotenv()
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Replace these with your own values from the Google Developer Console
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
DEBUG = os.getenv("debug",False)


@router.get("/login/google")
async def login_google():
    return {
        "url": f"https://accounts.google.com/o/oauth2/auth?response_type=code&client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&scope=openid%20profile%20email%20https://www.googleapis.com/auth/gmail.readonly&access_type=offline&prompt=consent"
    }


@router.get("/auth/google")
async def auth_google(code: str):
    token_url = "https://accounts.google.com/o/oauth2/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"    }
    response = requests.post(token_url, data=data)
    access_token = response.json().get("access_token")
    refresh_token = response.json().get("refresh_token")
    
    print(response.json())
    user_info = requests.get("https://www.googleapis.com/oauth2/v1/userinfo",
                             headers={"Authorization": f"Bearer {access_token}"})
    if user_info.status_code == 200:
        user_data = user_info.json()
        email = user_data.get('email')
        update_access_token(email=email, access_token=access_token,refresh_token=refresh_token)
        if DEBUG:
            return RedirectResponse('http://localhost:3000/dashboard')
        return RedirectResponse('https://askmail.ai/dashboard')
    else:
        raise HTTPException(status_code=401, detail="Invalid Token")


@router.get("/token")
async def get_token(token: str = Depends(oauth2_scheme)):
    return jwt.decode(token, GOOGLE_CLIENT_SECRET, algorithms=["HS256"])


@router.post("/login", response_model=Login)
def login(user: Token, authorize: AuthJWT = Depends()):
    if user.email and user.password:
        db_user = get_user(user.email)
        if db_user and verify_password(user.password, db_user.password):

            access_token = authorize.create_access_token(subject=user.email)
            refresh_token = authorize.create_refresh_token(subject=user.email)
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
            }
    raise HTTPException(status_code=401, detail="Bad username or password")


@router.post("/refresh", response_model=Refresh)
def refresh(authorize: AuthJWT = Depends()):
    authorize.jwt_refresh_token_required()

    current_user = authorize.get_jwt_subject()
    new_access_token = authorize.create_access_token(subject=current_user)
    return {"access_token": new_access_token, "token_type": "bearer"}


#
@router.get("/me", response_model=User)
def protected(authorize: AuthJWT = Depends()):
    authorize.jwt_required()

    current_user = authorize.get_jwt_subject()
    user = get_user(current_user)
    return User(**user.__dict__)


@router.post("/register", response_model=User)
def protected(user: Register):
    db_user = get_user(user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="This email already register.")
    new_user = Register(
        password=user.password,
        email=user.email,
    )
    user = add_user(new_user)
    return User(**user.__dict__)


@router.get("/download-pdf")
async def protected(email: str,db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user = get_user(current_user)

    try:
        creds = Credentials(
            token=user.access_token,
            scopes=['https://www.googleapis.com/auth/gmail.readonly']
        )

        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', q=f"from:{email}").execute()
        messages = results.get('messages', [])
    except:
        token_endpoint = 'https://oauth2.googleapis.com/token'
        params = {
                'refresh_token': user.refresh_token,
                'client_id': GOOGLE_CLIENT_ID,
                'client_secret': GOOGLE_CLIENT_SECRET,
                'grant_type': 'refresh_token'
            }

        response = requests.post(token_endpoint, data=params)
        if response.status_code == 200:
            new_access_token = response.json()['access_token']
            update_access_token(email=email, access_token=new_access_token,refresh_token=user.refresh_token)
            try:
                creds = Credentials(
                token=new_access_token,
                scopes=['https://www.googleapis.com/auth/gmail.readonly']
            )

                service = build('gmail', 'v1', credentials=creds)
                results = service.users().messages().list(userId='me', q=f"from:{email}").execute()
                messages = results.get('messages', [])
            except:
                raise HTTPException(status_code=400, detail="Token expired again connect google")   
        else:
            print(f'Error: {response.status_code} - {response.text}')
            raise HTTPException(status_code=400, detail="Token expired again connect google")
    content = ""
    if not messages:
        return {"message": 'No messages found.'}
    else:
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            subject = get_email_subject(msg)
            body = get_email_body(msg)
            email_from = get_email_from(msg)
            email_to = get_email_to(msg)
            date = get_email_date(msg)
            body = body if body else "No text"
            html_content = f"<h3>Email Subject: {subject}</h3><h3>From: {email_from}</h3><h3>To: {email_to}</h3><h3>Email Date: {date}</h3> <p>{body}</p><br>"
            content += html_content
        if content:
            html_content += f"<html><body>{content}</body></html>"
            data_id = await generate_unique_uuid(db)
            file_name = f'{email}_{data_id}.pdf'
            pdf_folder_path = f'media/{user.id}/{data_id}'
            downloaf_url = f'/download-pdf/{user.id}/{data_id}/{file_name}/' 
            # save pdf
            pdf_buffer = BytesIO()
            pisa_status = pisa.CreatePDF(html_content, dest=pdf_buffer)
            if pisa_status.err:
                print(f"Failed to generate PDF: {pisa_status.err}")
                return
            
            os.makedirs(pdf_folder_path, exist_ok=True)
            file_path = os.path.join(pdf_folder_path, file_name)

            pdf_buffer.seek(0)
            with open(file_path, 'wb') as pdf_file:
                pdf_file.write(pdf_buffer.read())
            # pdf_output_path = f'{email}_emails.pdf'
            # pdfkit.from_string(html_content, pdf_output_path)
            # pdfkit.from_string(html_content, pdf_output_path, configuration=pdfkit.configuration(wkhtmltopdf='C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe'))
            # return FileResponse(pdf_output_path, filename=f'{email}_emails.pdf', media_type="application/pdf")
            return JSONResponse(
                content={"download_url": downloaf_url},
                status_code=200,
            )
        
        return {"message": 'No messages found.'}

@router.get("/download-pdf/{user_id}/{data_id}/{file_name}/")
async def download_pdf(user_id: str,data_id: str, file_name: str,authorize: AuthJWT = Depends()):
    # Assuming you have a function to check if the user has permission to download the file
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user = get_user(current_user)
    if not user.id != (user_id):
        return JSONResponse(
                content={"error": "User is not authorize"},
                status_code=401,
            )
        
    file_path = f'media/{user.id}/{data_id}/{file_name}'
    if not os.path.isfile(file_path):
        return JSONResponse(
            content={"error":"File not exists"},
            status_code=404
        )
    return FileResponse(file_path, filename=file_name, media_type="application/pdf")