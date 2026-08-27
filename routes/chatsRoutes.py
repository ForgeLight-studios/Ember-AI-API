import logging
import sqlite3

from DbAccess import get_db
from fastapi import APIRouter, Depends
import json
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chats"
)

class ChatMessage(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    model: str


class Chat(BaseModel):
    id: str
    title: str

@router.post("/createChat")
def newChat(body: Chat, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - createChat] Starting endpoint")
    try:
        logger.info("[Server - createChat] Attempting to create a new chat. NAME: body.name")
        cur = conn.execute("INSERT INTO chats (id, title) VALUES(?, ?)", (body.id. body.title))
    except sqlite3.IntegrityError as e:
        logger.warning("[Server - createChat] Failed to create the new chat")
        conn.rollback()
        return JSONResponse(
            status_code=409,
            content={"success": False, "reason": "Internal Error"}
        )
    except sqlite3.Error as e:
        conn.rollback()
        return JSONResponse(
            status_code= 500,
            content= {"success": False, "reason": "internal server error"}
        )
    conn.commit()



@router.get("/getAllChats")
def getAllChats(conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - getAllChats] Starting endpoint")
    try:
        cur = conn.execute('''SELECT
                                c.id    AS chat_id,
                                c.title AS chat_title,
                                m.id    AS message_id,
                                m.role,
                                m.content,
                                m.model,
                                m.created_at
                            FROM chats c
                            JOIN messages m ON m.chat_id = c.id
                            ORDER BY c.updated_at DESC, m.created_at ASC;''')
        rows = cur.fetchall()

    except sqlite3.IntegrityError as e:
        logger.warning("[Server - getAllChats] This chat already exists")
        return JSONResponse(
            status_code= 409,
            content={"success": False, "reason": "This chat already exists"}
        )
    except sqlite3.Error as e:
        logger("[Server - getAllChats] There was an internal server error: &{e}")
        return JOSNResponse(
            status_code= 500,
            content= {"success": False, "reason": "e"}
        )

    chats = {}
    for row in rows:
        chat_id = row["chat_id"]
        if chat_id not in chats:
            chats[chat_id] = {"id": chat_id, "title": row["chat_title"], "messages": []}
        if row[messages_id] is not None:
            chats[chat_id].append({
                "id": row["message_id"],
                "role": row["content"],
                "model": row["model"],
                "created_at": row["created_at"]
            })
    results = list(chats.values())
    return JSONResponse(
        status_code= 200,
        content= {"success": True, "chats": results}
    )

