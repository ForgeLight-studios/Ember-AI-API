from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ollama
import logging as logger
import json

logger.basicConfig(
    level=logger.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%d-%m-%y %H:%M:%S",
)

# sets the value for the internal ollama server
OLLAMA_HOST = "http://localhost:11434"

client = ollama.Client(host=OLLAMA_HOST)
app = FastAPI(title="Ember AI API")

# sets teh cors middleware up
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# creates a defining class for what a model should look like
class ChatIn(BaseModel):
    model: str
    message: str
    # allows for a user to set the length of time a model stays alive for
    keep_alive: str = "30m"

# if starts up an ollama model if it has been pulled, and sends a message
@app.post("/api/chat")
def chat(body: ChatIn): # the ChatIn class here is a new object
    logger.info("[Server - chat] Starting endpoint.")
    try:
        logger.info("[Server - chat] Attempting to connect to the ollama server")
        resp = client.chat(
            model=body.model,
            messages=[{"role": "user", "content": body.message}],
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

# @app.get("/api/models/loaded"):
# def loaded_models():
    # This will return the number of models loaded when it is built.
    # The bash command for this is 'ollama ps'