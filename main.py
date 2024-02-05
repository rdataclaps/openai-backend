import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT
from fastapi_jwt_auth.exceptions import AuthJWTException

from config import settings
from database import engine, Base
from models.schemas import Settings
from routers import chat
from routers import vector, users, templates, auth

# Retrieve the OpenAI API key from the environment variable
openai_api_key = settings.OPENAI_API_KEY

app = FastAPI()
# app.openapi_url = "/api/docs"
# app.redoc_url = "/api/redoc"

Base.metadata.create_all(bind=engine)
app.include_router(chat.router, prefix="/api")
app.include_router(vector.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(auth.router, prefix="/api")

app.include_router(templates.router, prefix="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("healthchecker")
def root():
    return {"message": "working"}


@AuthJWT.load_config
def get_config():
    return Settings()


@app.exception_handler(AuthJWTException)
def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)

