from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging as logger
from DbAccess import init_db
from routes.ollamaRoutes import router as ollama_router
from routes.modelRoute import router as model_router
logger.basicConfig(
    level=logger.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%d-%m-%y %H:%M:%S",
)


app = FastAPI(
    title="Ember AI API"
)

app.include_router(ollama_router)
app.include_router(model_router)

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






