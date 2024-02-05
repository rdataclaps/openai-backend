from fastapi import Request, Depends, APIRouter
from fastapi_jwt_auth import AuthJWT

from services import get_user

router = APIRouter()


@router.get("/user")
async def get_user_data(request: Request, authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    return user_obj
