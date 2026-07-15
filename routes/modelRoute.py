import logging
import sqlite3

from DbAccess import get_db
from fastapi import APIRouter, Depends
import json
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class Model(BaseModel):
    name: str
    description: str
    status: str

class ModelStatus(BaseModel):
    name: str
    status: str

router = APIRouter(
    prefix="/model"
)

@router.post("/create")
def create_model(body: Model, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - create model] Endpoint started")
    try:
        logger.info("[Server - create model] attempting to connect to database")
        cur = conn.execute("INSERT INTO models (name, description, status) VALUES (?, ?, ?)", (body.name, body.description, body.status))
        conn.commit()
    except sqlite3.IntegrityError as e:
        logger.warning("[Server - create_model] duplicate model: %s\nError: %s", body.name, e)
        return JSONResponse(
            status_code=409,
            content={"success": False, "reason": f"model {body.name} already exists"}
        )
    except sqlite3.Error as e:
        logger.error("[Server - create_model] db error %s", e)
        conn.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "reason": "database error"}
        )
    return {"success": True, "name": body.name}

@router.patch("/status")
def update_status(body: ModelStatus, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - update_status] Starting endpoint")
    try:
        cur = conn.execute(
            "UPDATE models SET status = ? WHERE name = ?",
            (body.status, body.name),
        )
        conn.commit()
        if cur.rowcount == 0:
            logger.warning("[Server - update_status] no rows updated, model not found")
            return JSONResponse(status_code=404,
                content={"success": False, "reason": "model not found"})
    except sqlite3.Error as e:
        logger.error(f"[Server - update_status] failed to connect to database: {e}")

    logger.info("[Server - update_status] Successfully updated the install status for ", body.name)
    return {"success": True}

@router.get("/allmodels")
def get_all_models(conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - get_all_models] Starting endpoint")
    try:
        cur = conn.execute(
            "SELECT name, description, status FROM models"
        )
        rows = cur.fetchall()

    except sqlite3.Error as e:
        logger.info("[Server - get_all_models] Error collecting all models: %s", e)
        return JSONResponse(
            status_code=500,
            content=[{"success": False, "reason": "database error"}]
        )
    models = [dict(row) for row in rows]
    logger.info("[Server - get_all_models] Models retrieved\n%s", json.dumps(models))
    return {"success": True, "models": models}
