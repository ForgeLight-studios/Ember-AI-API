from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging as logger
from logging.handlers import RotatingFileHandler
from DbAccess import init_db
from routes.ollamaRoutes import router as ollama_router
from routes.modelRoute import router as model_router
from routes.chatsRoutes import router as chats_router

file_handler = RotatingFileHandler(
    "ember.log",
    maxBytes=5 * 1024 * 1024,   # 5 MB per file
    backupCount=3,               # keep ember.log.1 .. .3
)
file_handler.setFormatter(
    logger.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
)

logger.basicConfig(
    level=logger.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%d-%m-%y %H:%M:%S",
#     handlers=[file_handler, logger.StreamHandler()],
)

# for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
#     lg = logger.getLogger(name)
#     lg.handlers = [file_handler]
#     lg.propagate = False


app = FastAPI(
    title="Ember AI API"
)

app.include_router(ollama_router)
app.include_router(model_router)
app.include_router(chats_router)

@app.on_event("startup")
def startup():
    init_db()

# sets teh cors middleware up
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"]
)






