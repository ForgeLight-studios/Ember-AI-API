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

class Chat(BaseModel):
    id: str
    title: str
    model: str

@router.post('/createChat')
def newChat(body: Chat, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - createChat] Starting endpoint")
    try:
        logger.info("[Server - createChat] Attempting to create a new chat. NAME: " + body.title)
        conn.execute("INSERT INTO chats (id, title, model) VALUES(?, ?, ?)", (body.id, body.title, body.model))
    except sqlite3.Error as e:
        conn.rollback()
        return JSONResponse(
            status_code= 500,
            content= {"success": False, "reason": e}
        )
    conn.commit()
    return JSONResponse(
        status_code=200,
        content={"success": True}
    )

@router.post('/createMessage')
def newMessage(body: ChatMessage, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - createMessage] starting endpoint")
    try:
        conn.execute("INSERT INTO messages (id, chat_id, role, content) VALUES (?, ?, ?, ?)",
                     (body.id, body.chat_id, body.role, body.content))
    except sqlite3.IntegrityError as e:
        logger.error(f'[Server - createMessage] Error: {e}')
        return JSONResponse(
            status_code= 409,
            content= {"success": False, "reason": str(e)}
    )
    except sqlite3.Error as e:
        logger.error(f'[Server - createMessage] Error: {e}')
        return JSONResponse(
            status_code=500,
            content={"success": False, "reason": str(e)}
        )
    conn.commit()
    return JSONResponse(
        status_code=200,
        content={"success": True}
    )



@router.get('/getAllChats')
def getAllChats(conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - getAllChats] Starting endpoint")
    try:
        cur = conn.execute('''SELECT
                                c.id    AS chat_id,
                                c.title,
                                c.model,
                                m.id    AS message_id,
                                m.role,
                                m.content,
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
        logger.error(f'[Server - getAllChats] There was an internal server error: {e}')
        return JSONResponse(
            status_code= 500,
            content= {"success": False, "reason": str(e)}
        )

    chats = {}
    for row in rows:
        chat_id = row["chat_id"]
        if chat_id not in chats:
            chats[chat_id] = {"id": chat_id, "name": row["title"], "model": row["model"], "messages": []}
        if row["message_id"] is not None:
            chats[chat_id]["messages"].append({
                "id": row["message_id"],
                "role": row["role"],
                "content": row["content"],
            })
    results = list(chats.values())
    logger.info("[Server - getAllChats]" + json.dumps(results))
    return JSONResponse(
        status_code= 200,
        content= {"success": True, "chats": results}
    )

