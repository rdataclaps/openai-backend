from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT
from sqlalchemy.orm import Session

from database import get_db
from models import users
from services import get_user

router = APIRouter()


@router.post("/template")
async def create_template(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    title = data.get("title")
    questions = data.get("questions")
    user_id = user_obj.id

    # Create a new template
    template = users.Template(title=title, questions=questions, user_id=user_id)

    # Add the template to the database
    db.add(template)
    db.commit()
    db.refresh(template)

    return template


@router.get("/templates")
async def get_templates(request: Request, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    templates = (
        db.query(users.Template).filter(users.Template.user_id == user_obj.id).all()
    )
    return templates


@router.put("/template/{template_id}")
async def update_template(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    try:
        authorize.jwt_required()
        current_user = authorize.get_jwt_subject()
        user_obj = get_user(current_user)
        updated_title = data.get("title")
        updated_questions = data.get("questions")

        # Get template_id from the URL path parameters
        template_id_str = request.path_params.get("template_id")

        if template_id_str is None:
            return JSONResponse(
                content={"message": "Template ID not provided in query parameters"},
                status_code=400,
            )
        try:
            # Convert template_id to UUID
            template_id = UUID(template_id_str)
        except ValueError:
            return JSONResponse(
                content={"message": "Invalid UUID format"}, status_code=400
            )
        template = (
            db.query(users.Template)
            .filter_by(id=template_id, user_id=user_obj.id)
            .first()
        )
        if template is None:
            return JSONResponse(
                content={"message": "Template not found"}, status_code=404
            )
        template.title = updated_title
        template.questions = updated_questions
        db.commit()
        return {"message": "Template updated successfully"}

    except Exception as e:
        db.rollback()
        return JSONResponse(
            content={"message": "Internal server error"}, status_code=500
        )


@router.delete("/template/{template_id}")
async def delete_template(request: Request, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    try:
        authorize.jwt_required()
        current_user = authorize.get_jwt_subject()
        user_obj = get_user(current_user)

        # Get template_id from the URL path parameters
        template_id_str = request.path_params.get("template_id")

        if template_id_str is None:
            return JSONResponse(
                content={"message": "Template ID not provided in query parameters"},
                status_code=400,
            )
        try:
            # Convert template_id to UUID
            template_id = UUID(template_id_str)
        except ValueError:
            return JSONResponse(
                content={"message": "Invalid UUID format"}, status_code=400
            )

        template = db.query(users.Template).filter_by(id=template_id).first()
        if template is None:
            return JSONResponse(
                content={"message": "Template not found"}, status_code=404
            )

        db.delete(template)
        db.commit()
        return {"message": "Template deleted successfully"}

    except Exception as e:
        print(f"Exception: {type(e).__name__}, Message: {str(e)}")
        db.rollback()
        return JSONResponse(
            content={"message": "Internal server error"}, status_code=500
        )
