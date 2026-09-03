import logging
import sqlite3
from plistlib import dumps
from services import deleteOllamaModel, insert_model, getInstalledModels
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

class ModelPatch(BaseModel):
    attributeValue: str
    name: str
    attribute: str

router = APIRouter(
    prefix="/model"
)

@router.post("/create")
def create_model(body: Model, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - create model] Endpoint started")
    try:
        logger.info("[Server - create model] attempting to connect to database")
        insert_model(conn, body.name, body.description, body.status)
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

@router.patch("/patch")
def update_status(body: ModelPatch, conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - update_status] Starting endpoint")
    try:
        cur = conn.execute(
            f"UPDATE models SET {body.attribute} = ? WHERE name = ?",
            (body.attributeValue, body.name),
        )
        conn.commit()
        if cur.rowcount == 0:
            logger.warning("[Server - update_status] no rows updated, model not found")
            return JSONResponse(status_code=404,
                content={"success": False, "reason": "model not found"})
    except sqlite3.Error as e:
        logger.error(f"[Server - update_status] failed to connect to database: {e}")

    logger.info("[Server - update_status] Successfully updated the install status for %s", body.name)
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


@router.delete("/delete")
def deleteAModel(body: Model, conn: sqlite3.Connection = Depends(get_db)):
    logger.info(f"[Server - deleteModel] Starting endpoint: {body.name}")
    response = getInstalledModels()
    if not response.get("success"):
        return JSONResponse(
            status_code=500,
            content={"Success": False, "reason": "failed to contact the ollama service"}
        )
    isInstalled = any(m == body.name for m in response.get("models"))
    if isInstalled:
        result = deleteOllamaModel(body.name)
        if not result.get("success"):
            return JSONResponse(
                status_code=500,
                content={"success": False, "reason": "Could not access the ollama service"}
            )

    try:
        cur = conn.execute('DELETE FROM models WHERE name=?', (body.name,))
        if cur.rowcount > 1:
            conn.rollback()
            return JSONResponse(
                status_code=500,
                content={"success": False, "reason": "Multiple models matched; deletion aborted"}
            )
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"[Server - deleteModel] was unable to delete the model: " + str(e))
        conn.rollback()
        return JSONResponse(
            status_code=500,
            content={"success": False, "reason": e}
        )
    return JSONResponse(
        status_code=200,
        content={"success": True}
    )
