import asyncio
import datetime
import json
import os
import shutil
import traceback

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi_jwt_auth import AuthJWT
from langchain import LLMChain
from langchain.callbacks import get_openai_callback
from langchain.chat_models import ChatOpenAI
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.prompts import PromptTemplate
from langchain.vectorstores import FAISS
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from database import get_db
from models.users import (
    MessageType,
    UserCreditHistory,
    Chat,
    ChatMessage,
)
from services import get_user
from utils import (
    save_chat_message,
    format_page_content
)

router = APIRouter()


def log_error(customer_id, error_message, traceback_str):
    error_folder = "chat_error_logs"
    os.makedirs(error_folder, exist_ok=True)
    error_log_path = os.path.join(error_folder, f"error_log_{customer_id}.txt")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_log_path, "a") as error_log:
        error_log.write(f"[{timestamp}] {error_message}\n")
        error_log.write(traceback_str + "\n")


@router.get("/chat-messages")
async def get_chat_messages(
        request: Request,
        chat_id: str = Query(..., title="Chat ID from Query Parameter"),
        db: Session = Depends(get_db),
        authorize: AuthJWT = Depends()
):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    chat_id = chat_id
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.chat_id == chat_id)
        .order_by(asc(ChatMessage.updated_at))
        .all()
    )
    return messages


@router.get("/chat")
async def get_chat(request: Request, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    user_id = user_obj.id
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user_id)
        .order_by(desc(Chat.updated_at))
        .all()
    )
    return chats


@router.put("/chat")
async def update_chat_name(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    try:
        authorize.jwt_required()
        current_user = authorize.get_jwt_subject()
        user_obj = get_user(current_user)
        chat_id = data.get("id")
        updated_title = data.get("title")
        chat = db.query(Chat).filter_by(id=chat_id, user_id=user_obj.id).first()

        if chat is None:
            return JSONResponse(
                content={"status": "error", "message": "Chat not found"},
                status_code=404,
            )

        chat.title = updated_title
        db.commit()

        return {"message": "Chat title updated successfully"}

    except Exception as e:
        db.rollback()
        return JSONResponse(
            content={"status": "error", "message": "Internal server error"},
            status_code=500,
        )


@router.delete("/chat")
async def delete_chat_name(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    try:
        authorize.jwt_required()
        current_user = authorize.get_jwt_subject()
        user_obj = get_user(current_user)
        chat_id = data.get("chat_id")
        chat = db.query(Chat).filter_by(id=chat_id, user_id=user_obj.id).first()

        if chat is None:
            return JSONResponse(
                content={"status": "error", "message": "Chat not found"},
                status_code=404,
            )
        db.delete(chat)
        db.commit()
        db.close()

        return {"message": "Chat deleted successfully"}

    except Exception as e:
        db.rollback()
        return JSONResponse(
            content={"status": "error", "message": "Internal server error"},
            status_code=500,
        )


@router.post("/chat")
async def create_chat(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    title = data.get("title")
    chat_specific = data.get("chat_specific")
    if not title:
        title = "New chat"
    chat = Chat(title=title, chat_specific=chat_specific, user_id=user_obj.id)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.post("/chat/queries")
async def chat_chatbot(request: Request, data: dict, db: Session = Depends(get_db), authorize: AuthJWT = Depends()):
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)

    customer_id = user_obj.id
    queries_data = data.get("queries_data")

    async def process_query(qd):
        query = qd.get("query")
        data_ids = qd.get("data_ids")
        current_chat_id = qd.get("chat_id")
        chat_obj = db.query(Chat).filter(Chat.id == current_chat_id).first()

        if not chat_obj:
            return JSONResponse(
                content={"status": "error", "message": "This session not exist"},
                status_code=404,
            )

        # Get the 'context' value from the data dictionary
        # If not present, default to False
        context = qd.get("context", "false")
        context = context.lower()
        persist_directory = [
            f"trained_db/{customer_id}/{data_id}_all_embeddings" for data_id in data_ids
        ]
        temp_persist_directory = (
            f"temp_trained_db/{customer_id}/{current_chat_id}_all_embeddings"
        )
        temp_directory = f"temp_trained_db/{customer_id}"
        if not os.path.exists("chat"):
            os.makedirs("chat")

        if not os.path.exists(f"chat/{customer_id}"):
            os.makedirs(f"chat/{customer_id}")

        if not os.path.exists(f"chat/{customer_id}/data"):
            os.makedirs(f"chat/{customer_id}/data")

        # Define the path of the JSON file
        file_path = f"chat/{customer_id}/data/{current_chat_id}.json"

        # Check if the JSON file exists
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                f.write(json.dumps({"chat": []}))

        with open(file_path, "r") as f:
            chat_data = json.load(f)

        embeddings = OpenAIEmbeddings()
        llm = ChatOpenAI(temperature=0.1, model_name="gpt-3.5-turbo", max_tokens=2048)

        ANSWER_PROMPT = PromptTemplate(
            template=f"""\
            You are a chatbot assisting in a conversation with a human.

            Using both your built-in knowledge and the following extracted parts of a long document, please provide an answer to the given question.

            Your answer should be as detailed as possible if necessary.

            If the document does not contain relevant information for answering the question, please make that clear in your response.

            ---
            Context:

            ```
            {{context}}
            ```
            ---

            Question: {{question}}""",
            input_variables=["context", "question"],
        )
        answer_chain = LLMChain(llm=llm, prompt=ANSWER_PROMPT)

        try:
            indexes = [
                FAISS.load_local(filename, embeddings) for filename in persist_directory
            ]
        except Exception as e:
            if os.path.exists(temp_directory):
                shutil.rmtree(temp_directory)
            error_message = f"Error Loading Data: {str(e)}"
            traceback_str = traceback.format_exc()
            log_error(customer_id, error_message, traceback_str)
            return {"Error": "Error while loading data(embeddigs)"}

        # Aggregate the top 3 chunks from each document
        docs = [
            doc
            for index in indexes
            for doc in index.similarity_search_with_relevance_scores(query, k=3)
        ]
        # Sort the chunks by their relevance scores in descending order
        docs = sorted(docs, key=lambda x: x[1], reverse=True)
        # Select the first 3 chunks in total
        docs, _ = zip(*docs[:3])

        cost = 0

        for doc in docs:
            # Format page contents asynchronously
            formatted_result = await run_in_threadpool(
                format_page_content, doc.page_content
            )
            doc.page_content = formatted_result

        # Extract "page_content" from each Document and concatenate into a single string
        combined_page_content = "\n\n".join(doc.page_content for doc in docs)

        # Generate final answer
        with get_openai_callback() as cb:
            answer = answer_chain.run(
                {"context": combined_page_content, "question": query}
            )
            cost += cb.total_cost * 5 * 20

        user_obj.credit -= cost
        credit_history = UserCreditHistory(user_id=user_obj.id, credit=cost)
        db.add(credit_history)
        db.commit()
        try:
            db.refresh(user_obj)
        except Exception as e:
            print(e)

        db.refresh(credit_history)

        if os.path.exists(temp_directory):
            shutil.rmtree(temp_directory)

        # Save the query and answer in the JSON file
        chat_data["chat"].append({"user": query, "answer": answer})
        with open(file_path, "w") as f:
            json.dump(chat_data, f)

        if context == "false":
            save_chat_message(
                db=db,
                user_id=customer_id,
                chat_id=current_chat_id,
                message_text=query,
                message_type=MessageType.QUESTION,
            )
            save_chat_message(
                db=db,
                user_id=customer_id,
                chat_id=current_chat_id,
                message_text=answer,
                message_type=MessageType.ANSWER,
            )
            return {"question": query, "answer": answer, "credit": cost}

        elif context == "true":
            save_chat_message(
                db=db,
                user_id=customer_id,
                chat_id=current_chat_id,
                message_text=query,
                message_type=MessageType.QUESTION,
            )
            save_chat_message(
                db=db,
                user_id=customer_id,
                chat_id=current_chat_id,
                message_text=answer,
                message_type=MessageType.ANSWER,
                context_text=list(map(lambda doc: doc.page_content, docs)),
                message_metadata=list(map(lambda doc: doc.metadata, docs)),
            )
            return {
                "question": query,
                "answer": answer,
                "context": list(map(lambda doc: doc.page_content, docs)),
                "metadata": list(map(lambda doc: doc.metadata, docs)),
                "credit": cost,
            }

    futures = [process_query(qd) for qd in queries_data]
    responses = await asyncio.gather(*futures)
    db.commit()
    return responses


@router.get("/chat/download")
async def download_chat_data(
        request: Request,
        chat_id: str = Query(..., title="Chat ID from Query Parameter"),
        authorize: AuthJWT = Depends()
):
    # Define the path of the JSON file
    authorize.jwt_required()
    current_user = authorize.get_jwt_subject()
    user_obj = get_user(current_user)
    customer_id = user_obj.id
    file_path = f"chat/{customer_id}/data/{chat_id}.json"

    # Check if the JSON file exists
    if not os.path.exists(file_path):
        return {"message": f"JSON file for user '{customer_id}' not found."}

    # Provide the JSON file as a download
    return FileResponse(
        file_path, media_type="application/json", filename=f"{customer_id}.json"
    )
