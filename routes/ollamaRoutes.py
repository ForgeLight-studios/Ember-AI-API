import sqlite3
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from DbAccess import get_db
# from services import insert_model, client, current_pull
import services
from starlette.responses import StreamingResponse
import ollama
import logging, asyncio, json

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ollama"
)

class Message(BaseModel):
    role: str
    content: str

# creates a defining class for what a model should look like
class ChatIn(BaseModel):
    model: str
    messages: list[Message]
    # allows for a user to set the length of time a model stays alive for
    keep_alive: str

class PullModel(BaseModel):
    model: str

pullProgress: dict[str, dict] = {}

def doPull (model: str):
    """Runs in the background. Does NOT depend on any client connection."""
    pullProgress[model] = {"state": "pulling", "status": "starting", "completed": 0, "total": 0, "error": None}
    services.current_pull = {"name": model}
    try :
        for chunk in services.client.pull(model=model, stream=True):
            c = dict(chunk)
            pullProgress[model].update({
                "status": c.get("status", ""),
                "completed": c.get("completed") or 0,
                "total": c.get("total") or 0,
            })
        pullProgress[model].update({"state": "done", "status": "success"})
        logger.info("[Server - doPull] completed model=%s", model)
    except ollama.ResponseError as e:
        reason = f"model {model} not found" if e.status_code == 404 else f"ollama error: {e.error}"
        pullProgress[model].update({"state": "error", "error": reason})
        # update_model_status(model, "failed")
    except Exception as e:
        logger.exception("[do_pull] failed model=%s", model)
        pullProgress[model].update({"state": "error", "error": str(e)})
        # update_model_status(model, "failed")
    finally:
        services.current_pull = None

# it starts up an ollama model if it has been pulled, and sends a message
@router.post("/sendMessage")
def chat(body: ChatIn): # the ChatIn class here is a new object
    logger.info("[Server - chat] Starting endpoint.")
    try:
        logger.info("[Server - chat] Attempting to connect to the ollama server")
        resp = services.client.chat(
            model=body.model,
            messages=body.messages,
            # keeps that model alive for 30 minutes after the last message
            keep_alive=body.keep_alive
        )
    except ollama.ResponseError as e:
        # if the model has not been pulled returns a 404
        logger.error(f"[Server - chat] ollama model {body.model} has not been installed")
        if e.status_code == 404:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "reason": f"model: {body.model} is not installed",
                },
            )
        # global failure if ollama is not running or is not installed
        logger.error(f"[Server - chat] Could not access ollama server: {body.model} was not started")
        return JSONResponse(
            status_code=502,
            content={
                "success": False, "reason": "ollama host unreachable"
            }
        )
    # successful response for a message to a model
    logger.info(f"[Server - chat] Accessed {body.model} message has been sent - reply: \n\n {json.dumps(resp["message"]["content"], indent=2)}")
    return {
        "success": True,
        "model": body.model,
        "reply": resp["message"]["content"]
    }

@router.post("/pull")
def start_pull(body: PullModel, background: BackgroundTasks):
    services.current_pull = {"name": body.model}
    # avoid starting a duplicate pull for the same model
    existing = pullProgress.get(body.model)
    if existing and existing["state"] == "pulling":
        return JSONResponse({"success": True, "status": "already pulling"})
    background.add_task(doPull, body.model)
    return JSONResponse({"success": True, "status": "started"})

@router.get("/pull/progress/{model}")
async def pull_progress_stream(model: str):
    async def stream():
        last = None
        while True:
            state = pullProgress.get(model)
            if state is None:
                yield f"data: {json.dumps({'error': 'no such pull'})}\n\n"
                return
            # only emit when something changed
            if state != last:
                yield f"data: {json.dumps(state)}\n\n"
                last = dict(state)
            if state["state"] in ("done", "error"):
                return
            await asyncio.sleep(0.5)   # poll the shared state a couple times a second
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.get('/checkInstalled')
def checkInstalledModels(conn: sqlite3.Connection = Depends(get_db)):
    logger.info("[Server - checkInstalledModels] starting endpoint")
    modelsInstalled = services.client.list()
    logger.info(f"[Server - checkInstalledModels] Models already Installed\n{modelsInstalled}")
    if not len(modelsInstalled.models) > 0:
        return JSONResponse(
            status_code=200,
            content={"success": False, "reason": "No models to install"}
        )
    for model in modelsInstalled.models:
        try:
            services.insert_model(conn, model.model, "", "installed")
        except sqlite3.Error as e:
            logger.error(f"[Server - checkInstalledModels] Error adding models to the database {e}")
            conn.rollback()
    return JSONResponse (
        status_code= 200,
        content={"success": True}
    )



# @app.get("/api/models/loaded"):
# def loaded_models():
    # This will return the number of models loaded when it is built.
    # The bash command for this is 'ollama ps'