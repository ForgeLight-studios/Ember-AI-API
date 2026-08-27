# Ember AI API

The backend for **Ember AI**, a self-hosted, locally-hosted AI web app under [ForgeLight](https://github.com/ForgeLight-studios). It exposes a FastAPI service that proxies chat and model-management requests to a local [Ollama](https://ollama.com/) instance and persists chats, messages, and model metadata in SQLite.

## Features

- Chat with any locally installed Ollama model
- Pull new models from the Ollama registry with live streaming progress (Server-Sent Events)
- Track installed models and their install status (`pulling`, `installed`, `failed`) in SQLite
- Persist chats and messages with a normalised schema and cascade deletes
- Retrieve full chat history with messages via a single joined endpoint
- WAL journal mode and enforced foreign keys for safer concurrent access
- File-based logging with rotation, unified across the app and Uvicorn

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

## Logging

The app writes logs both to the console and to a rotating file, `ember.log`, so application and server output share one chronological record.

- Logging is configured once at startup via a single `logging.basicConfig` call with both a `RotatingFileHandler` and a `StreamHandler`. Note that `basicConfig` is a no-op if the root logger already has handlers, so it must not be called twice.
- The file handler rotates at 5 MB, keeping three backups (`ember.log.1` through `ember.log.3`).
- Uvicorn's own loggers (`uvicorn`, `uvicorn.access`, `uvicorn.error`) are routed to the same file handler so their output is interleaved with the app's in chronological order. Because `uvicorn.error` also carries general operational messages (startup, shutdown), it is kept rather than silenced.
- Log files are excluded from version control via `.gitignore` (`ember.log*`).

## Configuration

| Setting      | Where                        | Default                   |
|--------------|------------------------------|---------------------------|
| API port     | `EMBER_PORT` env var         | `3100`                    |
| Ollama host  | `OLLAMA_HOST` in `routes/ollamaRoutes.py` | `http://localhost:11434` |
| Database path| `DB_PATH` in `DbAccess.py`   | `ember.db`                |
| CORS origin  | `main.py`                    | `http://localhost:5173`   |
| Log file     | `main.py`                    | `ember.log`               |

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

Each SSE event is a `data:` line containing JSON. The stream ends with `{"done": true}`, or emits `{"error": "..."}` on failure (for example, when a model manifest is not found in the registry). Errors are streamed as `data:` chunks with a `200 OK` status rather than as a non-2xx response, so clients must inspect chunks for an `error` field rather than relying only on the HTTP status.

> **Note:** Pulling a model that is already installed is idempotent on Ollama's side; the pull completes with success rather than erroring. See Known issues for the status-handling gap this currently exposes.

### Model routes (`/model`)

#### `POST /model/create`

Register a model record in the database.

Request body:

```json
{
  "name": "llama3",
  "description": "Meta Llama 3 8B",
  "status": "pulling"
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

### Chat routes (`/chats`)

#### `POST /chats/createChat`

Create a new chat record.

Request body:

```json
{
  "id": "client-generated-id",
  "title": "New chat"
}
```

Responses:

- `200` — `{ "success": true }`
- `409` — chat already exists
- `500` — database error

#### `GET /chats/getAllChats`

Return every chat with its messages nested. The endpoint joins `chats` and `messages`, then groups the flat rows into one object per chat in the application layer (SQLite returns a flat row per message, so the nesting is assembled in Python).

Response:

```json
{
  "success": true,
  "chats": [
    {
      "id": "...",
      "title": "...",
      "messages": [
        {
          "id": "...",
          "role": "user",
          "content": "...",
          "model": "...",
          "created_at": "..."
        }
      ]
    }
  ]
}
```

> Requires `conn.row_factory = sqlite3.Row` so rows support named column access.

## Database schema

Defined in `db_sql/sql.sql`:

- **`models`** — `name` (PK), `description`, `status` (`pulling` | `installed` | `failed`), `created_at`
- **`chats`** — `id` (PK), `title`, `created_at`, `updated_at`
- **`messages`** — `id` (PK), `chat_id` (FK to `chats`, cascade delete), `role` (`user` | `assistant` | `system`), `content`, `model` (FK to `models`, set null on delete), `created_at`

Indexes on `messages(chat_id, created_at)` and `chats(updated_at DESC)`.

A trigger keeps `chats.updated_at` current whenever a message is inserted, so the `chats(updated_at DESC)` index stays meaningful for ordering the chat list:

```sql
CREATE TRIGGER IF NOT EXISTS touch_chat_on_message
AFTER INSERT ON messages
BEGIN
    UPDATE chats SET updated_at = datetime('now') WHERE id = NEW.chat_id;
END;
```

## Project structure

```
.
├── main.py                  # FastAPI app, router registration, CORS, logging, startup
├── run.py                   # Uvicorn entry point
├── DbAccess.py              # connection, get_db dependency, init_db
├── requirements.txt
├── db_sql/
│   └── sql.sql              # schema
└── routes/
    ├── ollamaRoutes.py      # chat and pull endpoints
    ├── modelRoute.py        # model CRUD endpoints
    └── chatsRoutes.py       # chat persistence endpoints
```

## Recent fixes

- **Already-installed pulls now settle correctly.** When a pull is requested for a model that already exists, the flow no longer leaves the model stuck at `pulling`; conflict handling and status correction settle the record on `installed`.

## Roadmap / planned work

- **Move model-pull DB writes server-side.** Currently the pull's completion and status update are driven by the client reading the SSE stream, so closing or refreshing the browser can interrupt the flow. The plan is to run the pull-and-persist as a background task independent of the streaming response, so pulls complete regardless of the client, with progress streaming becoming an optional view over server-owned state.