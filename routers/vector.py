import datetime
import os
import shutil
import traceback

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT
from langchain.docstore.document import Document
from langchain.document_loaders import UnstructuredWordDocumentLoader, PyPDFLoader
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import TokenTextSplitter
from langchain.vectorstores import FAISS
from sqlalchemy.orm import Session

from database import get_db
from models.users import UserTrainData
from services import get_user
from utils import (
    convert_size,
    create_train_data,
    generate_unique_uuid
)

load_dotenv()

router = APIRouter()


def log_error(customer_id, error_message, traceback_str):
    error_folder = "train_error_logs"
    os.makedirs(error_folder, exist_ok=True)
    error_log_path = os.path.join(error_folder, f"error_log_{customer_id}.txt")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_log_path, "a") as error_log:
        error_log.write(f"[{timestamp}] {error_message}\n")
        error_log.write(traceback_str + "\n")


@router.get("/get-train-data")
async def get_data(request: Request, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    existing_user_data = (
        db.query(UserTrainData).filter(UserTrainData.user_id == user_obj.id).all()
    )
    for item in existing_user_data:
        item.file_size = convert_size(item.file_size)
    return existing_user_data


@router.post("/train")
async def train(
        request: Request,
        file: UploadFile = File(...),
        chat_id: str = Form(...),
        db: Session = Depends(get_db),
        authorize: AuthJWT = Depends()

):
    if chat_id == "null":
        chat_id = None

    try:
        authorize.jwt_required()
        current_user = authorize.get_jwt_subject()
        user_obj = get_user(current_user)
        if user_obj.credit <= 0:
            return JSONResponse(
                content={"status": "error", "message": "Please recharge you wallet"},
                status_code=402,
            )

        customer_id = user_obj.id
        data_id = await generate_unique_uuid(db)
        persist_directory = f"trained_db/{customer_id}/{data_id}_all_embeddings"

        if file:
            filename = file.filename.lower()

            if filename.endswith(".pdf"):
                pdf_folder_path = f"pdf_temp_{customer_id}"
                os.makedirs(pdf_folder_path, exist_ok=True)
                file_path = os.path.join(pdf_folder_path, filename)

                with open(file_path, "wb") as f:
                    f.write(await file.read())

                data_size = os.path.getsize(file_path)

                try:
                    documents = PyPDFLoader(file_path).load()
                    text_splitter = TokenTextSplitter(
                        chunk_size=1024, chunk_overlap=256
                    )
                    split_docs = text_splitter.split_documents(documents)

                    for docs in split_docs:
                        docs.metadata["page"] = docs.metadata.get("page") + 1
                        docs.metadata["filename"] = filename

                    embeddings = OpenAIEmbeddings()

                    new_vectordb = FAISS.from_documents(split_docs, embeddings)
                    try:
                        old_vectordb = FAISS.load_local(persist_directory, embeddings)
                        old_vectordb.merge_from(new_vectordb)
                        old_vectordb.save_local(persist_directory)
                        print("Previous Embeddings were loaded.")
                    except:
                        new_vectordb.save_local(persist_directory)
                        print("New VectorStore is initialized")
                except Exception as e:
                    error_message = f"Error {str(e)}"
                    traceback_str = traceback.format_exc()
                    log_error(customer_id, error_message, traceback_str)
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "file upload unsuccessful",
                        },
                        status_code=400,
                    )

                except Exception as e:
                    # Log the traceback information to a file
                    error_message = (
                        f"Error processing PDF: {str(e)} \n s3 file upload error: {e}"
                    )
                    traceback_str = traceback.format_exc()
                    log_error(customer_id, error_message, traceback_str)
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "Rate Limit Reached For Your Account",
                        },
                        status_code=400,
                    )

                finally:
                    shutil.rmtree(pdf_folder_path)
                trained_data_object = await create_train_data(
                    db,
                    id=data_id,
                    source_filename=file.filename,
                    source_file_extensions=".pdf",
                    trained_data_path=persist_directory,
                    user_id=user_obj.id,
                    chat_id=chat_id,
                    file_size=data_size,
                )
                return {
                    "answer": "PDF EMBEDDINGS GENERATED SUCCESSFULLY",
                    "data": trained_data_object,
                }

            elif filename.endswith(".docx"):
                word_folder_path = f"word_temp_{customer_id}"
                os.makedirs(word_folder_path, exist_ok=True)
                file_path = os.path.join(word_folder_path, file.filename)

                try:
                    with open(file_path, "wb") as f:
                        f.write(await file.read())
                    file_size = os.path.getsize(file_path)

                    documents = UnstructuredWordDocumentLoader(file_path).load()
                    text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=0)
                    split_docs = text_splitter.split_documents(documents)
                    embeddings = OpenAIEmbeddings()
                    new_vectordb = FAISS.from_documents(split_docs, embeddings)
                    try:
                        old_vectordb = FAISS.load_local(persist_directory, embeddings)
                        old_vectordb.merge_from(new_vectordb)
                        old_vectordb.save_local(persist_directory)
                        print("Previous Embeddings were loaded.")
                    except:
                        new_vectordb.save_local(persist_directory)
                        print("New VectorStore is initialized")

                except Exception as e:
                    error_message = f"Error: {str(e)}"
                    traceback_str = traceback.format_exc()
                    log_error(customer_id, error_message, traceback_str)
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "file upload unsuccessful",
                        },
                        status_code=400,
                    )

                except Exception as e:
                    # Log the traceback information to a file
                    error_message = f"Error processing DOCX: {str(e)}"
                    traceback_str = traceback.format_exc()
                    log_error(customer_id, error_message, traceback_str)
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "Rate Limit Reached For Your Account",
                        },
                        status_code=400,
                    )

                finally:
                    shutil.rmtree(word_folder_path)
                trained_data_object = await create_train_data(
                    db,
                    id=data_id,
                    source_filename=file.filename,
                    source_file_extensions=".docx",
                    trained_data_path=persist_directory,
                    user_id=user_obj.id,
                    chat_id=chat_id,
                    file_size=file_size,
                )
                return {
                    "answer": "DOCX EMBEDDINGS GENERATED SUCCESSFULLY",
                    "data": trained_data_object,
                }

            elif filename.endswith(".xlsx"):
                excel_folder_path = f"excel_temp_{customer_id}"
                os.makedirs(excel_folder_path, exist_ok=True)
                file_path = os.path.join(excel_folder_path, file.filename)
                try:
                    with open(file_path, "wb") as f:
                        f.write(await file.read())

                    file_size = os.path.getsize(file_path)

                    # convert xlsx file to csv
                    df = pd.read_excel(file_path, header=None)
                    rows = df.apply(lambda row: f"{row[0]}: {row[1]}", axis=1).to_list()
                    # create documents from groups
                    documents = [Document(page_content=row) for row in rows]

                    embeddings = OpenAIEmbeddings()
                    new_vectordb = FAISS.from_documents(documents, embeddings)
                    try:
                        old_vectordb = FAISS.load_local(persist_directory, embeddings)
                        old_vectordb.merge_from(new_vectordb)
                        old_vectordb.save_local(persist_directory)
                        print("Previous Embeddings were loaded.")
                    except:
                        new_vectordb.save_local(persist_directory)
                        print("New VectorStore is initialized")

                except Exception as e:
                    error_message = f"Error : {str(e)}"
                    traceback_str = traceback.format_exc()
                    log_error(customer_id, error_message, traceback_str)
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "file upload unsuccessful",
                        },
                        status_code=400,
                    )

                except Exception as e:
                    # Log the traceback information to a file
                    error_message = (
                        f"Error processing XLSX: {str(e)} \n s3 file upload error: {e}"
                    )
                    traceback_str = traceback.format_exc()
                    log_error(customer_id, error_message, traceback_str)
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "Rate Limit Reached For Your Account",
                        },
                        status_code=400,
                    )

                finally:
                    shutil.rmtree(excel_folder_path)

                trained_data_object = await create_train_data(
                    db,
                    id=data_id,
                    source_filename=file.filename,
                    source_file_extensions=".xlsx",
                    trained_data_path=persist_directory,
                    user_id=user_obj.id,
                    chat_id=chat_id,
                    file_size=file_size,
                )
                return {
                    "answer": "XLSX EMBEDDINGS GENERATED SUCCESSFULLY",
                    "data": trained_data_object,
                }

        else:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": "ONLY PDF, DOCX, XLSX FILE ALLOWED",
                },
                status_code=400,
            )

    except Exception as e:
        # Log the traceback information for the general error
        error_message = f"General Error: {str(e)}"
        traceback_str = traceback.format_exc()
        log_error(customer_id, error_message, traceback_str)
        return JSONResponse(
            content={
                "status": "error",
                "message": "An error occurred. Please check the logs.",
            },
            status_code=400,
        )


@router.post("/train/delete")
async def deletetxt(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    data_id = data.get("data_id")
    file_name = data.get("file_name")
    customer_id = data.get("customer_id")
    if file_name and customer_id and data_id:
        try:
            user_train_data = (
                db.query(UserTrainData)
                .filter_by(user_id=customer_id, id=data_id)
                .first()
            )
            if user_train_data is None:
                return JSONResponse(
                    content={"status": "error", "message": "User train data not found"},
                    status_code=404,
                )
            db.delete(user_train_data)
            db.commit()
        except Exception as e:
            traceback_str = traceback.format_exc()
            log_error(customer_id, e, traceback_str)
            return JSONResponse(
                content={"status": "error", "message": "something went wrong"},
                status_code=400,
            )

        return JSONResponse(
            content={"message": "User train data deleted successfully"}, status_code=200
        )

    else:
        return JSONResponse(
            content={
                "status": "error",
                "message": f"No embeddings found for data id : {data_id} and customer id {customer_id}",
            },
            status_code=400,
        )
