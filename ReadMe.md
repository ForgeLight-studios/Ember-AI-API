# Ember AI API

The backend for **Ember AI**, a self-hosted, locally-hosted AI web app under [ForgeLight](https://github.com/ForgeLight-studios). It exposes a FastAPI service that proxies chat and model-management requests to a local [Ollama](https://ollama.com/) instance and persists chats, messages, and model metadata in SQLite.

## Features

- Chat with any locally installed Ollama model
- Pull new models from the Ollama registry with live streaming progress (Server-Sent Events)
- Track installed models and their install status (`pulling`, `installed`, `failed`) in SQLite
- Persist chats and messages with a normalised schema and cascade deletes
- WAL journal mode and enforced foreign keys for safer concurrent access

## Tech stack

- **Python** with **FastAPI** and **Uvicorn**
- **Ollama** Python client for model inference and pulls
- **SQLite** for persistence
- **Pydantic** for request validation

## Requirements

- Python 3.9+
- A running Ollama server (defaults to `http://localhost:11434`)

## Installation

```bash
# clone and enter the repo
git clone <repo-url>
cd <repo>

# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt
```

Make sure Ollama is installed and running before starting the API:

```bash
ollama serve
```

## Running

```bash
python run.py
```

By default this starts the server on `http://localhost:3100` with auto-reload enabled. The port can be overridden with the `EMBER_PORT` environment variable:

```bash
EMBER_PORT=8080 python run.py
```

On startup the app runs `init_db()`, which applies the schema in `db_sql/sql.sql` and creates `ember.db` if it does not already exist.

> **Note:** CORS is configured to allow requests from `http://localhost:5173` (the Vite/React frontend dev server).

## Configuration

| Setting      | Where                        | Default                   |
|--------------|------------------------------|---------------------------|
| API port     | `EMBER_PORT` env var         | `3100`                    |
| Ollama host  | `OLLAMA_HOST` in `routes/ollamaRoutes.py` | `http://localhost:11434` |
| Database path| `DB_PATH` in `DbAccess.py`   | `ember.db`                |
| CORS origin  | `main.py`                    | `http://localhost:5173`   |

## API reference

### Ollama routes (`/ollama`)

#### `POST /ollama/newChat`

Send a message to a model. Starts the model if it has been pulled.

Request body:

```json
{
  "model": "llama3",
  "message": "Hello there",
  "keep_alive": "30m"
}
```

- `keep_alive` is optional and defaults to `"30m"` (how long the model stays loaded after the last message).

Responses:

- `200` — `{ "success": true, "model": "...", "reply": "..." }`
- `404` — model not installed
- `502` — Ollama host unreachable

#### `POST /ollama/pull`

Pull a model from the Ollama registry. Returns a streaming `text/event-stream` response with progress chunks.

Request body:

```json
{ "model": "llama3" }
```

Each SSE event is a `data:` line containing JSON. The stream ends with `{"done": true}`, or emits `{"error": "..."}` on failure (for example, a `404` when the model is not found in the registry).

### Model routes (`/model`)

#### `POST /model/create`

Register a model record in the database.

Request body:

```json
{
  "name": "llama3",
  "description": "Meta Llama 3 8B",
  "status": "installed"
}
```

Responses:

- `200` — `{ "success": true, "name": "..." }`
- `409` — model already exists
- `500` — database error

#### `PATCH /model/status`

Update the install status of a model.

Request body:

```json
{
  "name": "llama3",
  "status": "installed"
}
```

Responses:

- `200` — `{ "success": true }`
- `404` — model not found

#### `GET /model/allmodels`

Return all registered models.

Response:

```json
{
  "success": true,
  "models": [
    { "name": "...", "description": "...", "status": "..." }
  ]
}
```

## Database schema

Defined in `db_sql/sql.sql`:

- **`models`** — `name` (PK), `description`, `status` (`pulling` | `installed` | `failed`), `created_at`
- **`chats`** — `id` (PK), `title`, `created_at`, `updated_at`
- **`messages`** — `id` (PK), `chat_id` (FK to `chats`, cascade delete), `role` (`user` | `assistant` | `system`), `content`, `model` (FK to `models`, set null on delete), `created_at`

Indexes on `messages(chat_id, created_at)` and `chats(updated_at DESC)`.

## Project structure

```
.
├── main.py                  # FastAPI app, router registration, CORS, startup
├── run.py                   # Uvicorn entry point
├── DbAccess.py              # connection, get_db dependency, init_db
├── requirements.txt
├── db_sql/
│   └── sql.sql              # schema
└── routes/
    ├── ollamaRoutes.py      # chat and pull endpoints
    └── modelRoute.py        # model CRUD endpoints
```

## License

Part of the ForgeLight studio. Add your chosen license here.