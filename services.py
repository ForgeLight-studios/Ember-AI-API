import logging
import sqlite3
import json
import ollama
from fastapi import Depends

from DbAccess import get_db, connect

logger = logging.getLogger(__name__)
# conn = sqlite3.Connection
# sets the value for the internal ollama server
OLLAMA_HOST = "http://localhost:11434"

client = ollama.Client(host=OLLAMA_HOST)

current_pull: dict | None = None
# a plain helper — takes conn + values, no Pydantic, no Depends
def insert_model(conn, name, description, status):
    logger.info(f"[Server - insert_model] Inserting: {json.dumps({"model": name, "description": description})}")
    try:
        conn.execute(
            "INSERT OR IGNORE INTO models (name, description, status) VALUES (?, ?, ?)",
            (name, description, status)
        )
        logger.info(f"[Server - insert_model] Added model: {name} to the database")
        conn.commit()
    except sqlite3.InternalError as e:
        logger.warning(f"[Server - insert_model] Integrity error when inserting model: {name}")
        conn.rollback()
    except sqlite3.Error as e :
        logger.error(f"[Server - insert_model] Internal server error: {e}")
        conn.rollback()

def deleteOllamaModel(modelName):
    try:
        client.delete(modelName)
    except ollama.ResponseError as e:
        logger.error(f"[Server - deleteOllamaModel ] Ollama rejected delete for {modelName!r}: status={e.status_code} error={e.error}")
        return {
            "status_code": e.status_code,
            "success": False
        }
    return {
        "status_code": 200,
        "success": True
    }

def getInstalledModels():
    try:
        installed = client.list()
        return {
            "success": True,
            "models": [m.model for m in installed.models]
        }
    except ollama.ResponseError as e:
        return {
            "success": False
        }

def checkInstalledModels():
    conn = connect()
    logger.info("[Server - checkInstalledModels] Getting installed models")
    try:
        modelsInstalled = client.list()
    except Exception as e:
        logger.warning(f"[ Server - checkInstalledModels ] Could not access the ollama service: {e}")
        conn.close()
        return
    logger.info("[Server - checkInstalledModels] Models installed: %s",[m.model for m in modelsInstalled.models])
    if not modelsInstalled or not len(modelsInstalled.models) > 0:
        conn.close()
        return
    for model in modelsInstalled.models:
        try:
            insert_model(conn, model.model, "", "installed")
        except sqlite3.Error as e:
            logger.error(f"[Server - checkInstalledModels] Error adding models to the database {e}")
            conn.rollback()
    conn.close()
    return