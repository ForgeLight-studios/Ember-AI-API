# Ember AI API

The backend for **Ember AI**, a self-hosted, locally-hosted AI web app under [ForgeLight](https://github.com/ForgeLight-studios). It exposes a FastAPI service that proxies chat and model-management requests to a local [Ollama](https://ollama.com/) instance and persists chats, messages, and model metadata in SQLite.

## Features

- Chat with any locally installed Ollama model, sending prior turns so the model has conversation context
- Pull new models from the Ollama registry as a server-side background task, with live progress over Server-Sent Events that any client can attach to or reconnect to
- Track installed models and their install status (`pulling`, `installed`, `failed`) in SQLite
- Delete models from both Ollama and the database, tolerating models already gone from Ollama
- Sync Ollama's installed models into the database on startup
- Persist chats and messages with a normalised schema and cascade deletes
- Retrieve chat history with messages via a single joined endpoint
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

This starts the server on `http://0.0.0.0:3100` (all interfaces, so other devices on the network can reach it) with auto-reload enabled. The port can be overridden with the `EMBER_PORT` environment variable:

```bash
EMBER_PORT=8080 python run.py
```

On startup the app runs `init_db()` (applies the schema in `db_sql/sql.sql`, creating `ember.db` if absent) and then `checkInstalledModels()` (see Startup sync).

> **Note:** CORS is configured to allow all origins, so the frontend can reach the API from another device on the local network (e.g. a phone at `http://<machine-ip>:5173`).

## Startup sync

On startup the app calls `checkInstalledModels()` (in `services.py`), which asks Ollama for its installed models (`client.list()`) and inserts any it doesn't already have into the `models` table with status `installed`. Inserts use `INSERT OR IGNORE`, so running the sync repeatedly does not create duplicates.

This is wrapped so a failure never aborts startup: the `client.list()` call catches all exceptions (not only `ollama.ResponseError`), so an unreachable Ollama logs a warning and the server still boots. This matters because an unhandled exception in the FastAPI startup event causes Uvicorn to report "Application startup failed. Exiting."

The `/ollama/checkInstalled` HTTP endpoint that previously exposed this is currently commented out; the sync runs on startup only.

> **Known limitation:** Ollama reports full tags (e.g. `llama3.1:latest`) while older database rows may hold bare names (e.g. `llama3.1`), so the two can coexist as separate rows. A future reconciliation pass (canonicalising on the full tag and pruning stale rows) is planned; see Roadmap.

## Logging

Logging is configured in `main.py` with a single `logging.basicConfig` using both a `RotatingFileHandler` (writing `ember.log`) and a `StreamHandler` (console).

- The file handler rotates at 5 MB, keeping three backups (`ember.log.1` through `ember.log.3`).
- `basicConfig` is a no-op if the root logger already has handlers, so it must not be called twice.
- Uvicorn's `uvicorn.error` logger is its general operational logger, not an errors-only one: messages like "Application startup complete" come through it at `INFO` level. Read the level column, not the logger name, to judge severity.
- Log files are excluded from version control via `.gitignore` (`ember.log*`).

## Configuration

| Setting      | Where                          | Default                   |
|--------------|--------------------------------|---------------------------|
| API port     | `EMBER_PORT` env var           | `3100`                    |
| Ollama host  | `OLLAMA_HOST` in `services.py`  | `http://localhost:11434` |
| Database path| `DB_PATH` in `DbAccess.py`     | `ember.db`                |
| Log file     | `main.py`                      | `ember.log`               |

## API reference

### Ollama routes (`/ollama`)

#### `POST /ollama/sendMessage`

Send a conversation to a model and get its reply. Starts the model if it has been pulled. The full message history is sent, so the model has context from earlier turns.

Request body:

```json
{
  "model": "llama3",
  "messages": [ { "role": "user", "content": "Hello there" } ],
  "keep_alive": "30m"
}
```

- `messages` is the ordered conversation so far; each entry has a `role` (`user` | `assistant` | `system`) and `content`.
- `keep_alive` sets how long the model stays loaded after the last message.

Responses:

- `200` — `{ "success": true, "model": "...", "reply": "..." }`
- `404` — model not installed
- `502` — Ollama host unreachable

#### `POST /ollama/pull`

Start pulling a model from the Ollama registry. The pull runs as a **server-side background task** (`doPull`) that is independent of the HTTP response, so it completes even if the client disconnects, refreshes, or closes. Returns immediately. On completion it inserts the model into the database with status `installed`. Progress is written into an in-memory `pullProgress` map keyed by model name, and the currently-pulling model is tracked in `services.current_pull`.

Request body:

```json
{ "name": "llama3", "description": "optional description" }
```

Responses:

- `200` — `{ "success": true, "status": "started" }` (or `"already pulling"` if a pull for that model is already in progress)

#### `GET /ollama/pull/progress/{model}`

Stream live progress for a running pull as Server-Sent Events. Any client, on any device, can connect to watch; if it disconnects, the pull keeps running and the client can reconnect and pick up the current state.

Each event is a `data:` line with the current state, e.g.:

```json
{ "state": "pulling", "status": "downloading", "completed": 12345, "total": 67890, "error": null }
```

The stream ends when `state` becomes `done` or `error`. It only reads server-owned state, so it is a passive view over the background pull, not the thing driving it. (If no pull entry exists for that model, it emits `{"error": "no such pull"}` and closes.)

### Model routes (`/model`)

#### `POST /model/create`

Register a model record in the database.

Request body:

```json
{ "name": "llama3", "description": "Meta Llama 3 8B", "status": "pulling" }
```

Responses:

- `200` — `{ "success": true, "name": "..." }`
- `409` — model already exists
- `500` — database error

#### `PATCH /model/patch`

Update a single attribute of a model record (e.g. `status` or `description`). The column name is taken from `attribute`.

Request body:

```json
{ "name": "llama3", "attribute": "status", "attributeValue": "installed" }
```

Responses:

- `200` — `{ "success": true }`
- `404` — model not found

#### `GET /model/allmodels`

Return all registered models, plus the currently-pulling model from server state so any client can learn on load whether a pull is in progress and reconnect to it.

Response:

```json
{
  "success": true,
  "models": [ { "name": "...", "description": "...", "status": "..." } ],
  "pulling": { "name": "llama3", "description": "..." }
}
```

`pulling` is `services.current_pull` (the pulling model object) or `null` when nothing is pulling.

#### `DELETE /model/delete`

Delete a model from both Ollama and the database. Checks whether the model is installed in Ollama first (`getInstalledModels`); if so, deletes it there, then nulls the model reference on any chats that used it (`UPDATE chats SET model = NULL WHERE model = ?`) and deletes the model row.

Request body: a full model object (`{ "name", "description", "status" }`); only `name` is used.

Responses:

- `200` — `{ "success": true }`
- `500` — could not reach Ollama, multiple rows matched, or a database error

### Chat routes (`/chats`)

#### `POST /chats/createChat`

Create a new chat record. Must be called before any message referencing the chat is inserted, since `messages.chat_id` has a foreign key to `chats.id`.

Request body:

```json
{ "id": "client-generated-id", "title": "Chat title", "model": "llama3" }
```

Responses:

- `200` — `{ "success": true }`
- `500` — database error

#### `POST /chats/createMessage`

Persist a single message against an existing chat. The chat row must already exist, or the insert fails with a foreign-key constraint error.

Request body:

```json
{ "id": "client-generated-id", "chat_id": "owning-chat-id", "role": "user", "content": "Hello there" }
```

Responses:

- `200` — `{ "success": true }`
- `409` — integrity error (e.g. foreign-key constraint failed when the chat does not exist)
- `500` — database error

> Both `createChat` and `createMessage` call `conn.commit()` after the insert; without it the write is discarded when the request's connection is torn down.

#### `PATCH /chats/patch`

Update a single attribute of a chat (e.g. `title`). The column name is taken from `attribute`.

Request body:

```json
{ "id": "chat-id", "attribute": "title", "attributeValue": "New title" }
```

Responses:

- `200` — `{ "success": true }`
- `404` — chat not found

#### `DELETE /chats/delete`

Delete a chat by id. Its messages are removed automatically by the `ON DELETE CASCADE` on `messages.chat_id` (foreign keys are enabled per connection).

Request body: a chat object (`{ "id", "title", "model" }`); only `id` is used.

Responses:

- `200` — `{ "success": true }`
- `404` — chat not found
- `500` — more than one row matched, or a database error

#### `GET /chats/getAllChats`

Return chats with their messages nested. The endpoint uses an **INNER JOIN** between `chats` and `messages`, then groups the flat rows into one object per chat in the application layer (SQLite returns a flat row per message, so the nesting is assembled in Python).

Because it is an inner join, **a chat with no messages is not returned** (see Known issues).

Response:

```json
{
  "success": true,
  "chats": [
    {
      "id": "...",
      "name": "...",
      "model": "...",
      "messages": [ { "id": "...", "role": "user", "content": "..." } ]
    }
  ]
}
```

> Requires `conn.row_factory = sqlite3.Row` (set in `connect()`) so rows support named column access. Note the chat's title is returned under the key `name`.

## Database schema

Defined in `db_sql/sql.sql`:

- **`models`** — `name` (PK), `description` (NOT NULL), `status` (`pulling` | `installed` | `failed`, default `installed`), `created_at`
- **`chats`** — `id` (PK), `title`, `model` (plain `TEXT`, no foreign key), `created_at`, `updated_at`
- **`messages`** — `id` (PK), `chat_id` (FK to `chats(id)`, `ON DELETE CASCADE`), `role` (`user` | `assistant` | `system`), `content` (NOT NULL), `created_at`

`chats.model` is a plain `TEXT` column with **no** foreign key to `models`. This is deliberate: the model name must survive the model being deleted so the frontend can tell the user which (now-deleted) model a chat used. (When a model is deleted, `/model/delete` explicitly nulls `chats.model` for affected chats.) There is **no** `model` column on `messages`.

Indexes: `idx_messages_chat` on `messages(chat_id, created_at)` and `idx_chats_updated` on `chats(updated_at DESC)`.

> Note: `chats.updated_at` is not currently maintained by a trigger; if chat-list ordering by recency matters, update `updated_at` on message insert (via a trigger or in `createMessage`).

## Project structure

```
.
├── main.py                  # FastAPI app, router registration, CORS, logging, startup (init_db + model sync)
├── run.py                   # Uvicorn entry point (host 0.0.0.0)
├── DbAccess.py              # connect(), get_db dependency, init_db
├── services.py              # ollama client, current_pull state, insert_model, delete/list helpers, startup sync
├── requirements.txt
├── db_sql/
│   └── sql.sql              # schema
└── routes/
    ├── ollamaRoutes.py      # chat, pull (background task) + progress SSE, pullProgress state
    ├── modelRoute.py        # model create/patch/list/delete
    └── chatsRoutes.py       # chat + message create, list, patch, delete
```

Shared server-side state (`current_pull`, the Ollama `client`, `insert_model`, delete/list helpers) lives in `services.py` so route modules can use it without importing each other (which would create a circular import). `current_pull` is written through the module (`services.current_pull = ...`) and read the same way; importing it by value (`from services import current_pull`) would take a stale snapshot that never sees updates. `pullProgress` lives in `ollamaRoutes.py` and is mutated in place.

## Recent work

- **Server-side pulls with reconnectable progress.** Pulls run as background tasks independent of the client connection, so they complete through a refresh or disconnect. Progress is exposed as an SSE stream over server-owned state, and `allmodels` reports the currently-pulling model so any client can reconnect on load. (This was the previous roadmap item.)
- **Model deletion.** `DELETE /model/delete` removes the model from Ollama and the database, nulls it on any chats that referenced it, and tolerates a model already gone from Ollama.
- **Startup model sync made resilient.** `checkInstalledModels` runs on startup and catches connection failures (not only `ollama.ResponseError`), so an unreachable Ollama logs a warning rather than aborting startup.
- **`chats.model` foreign key removed.** Changed to a plain `TEXT` column so a chat retains its model name after that model is deleted; the delete endpoint nulls it explicitly.
- **Chat delete and patch, model patch.** Added `DELETE /chats/delete`, `PATCH /chats/patch`, and `PATCH /model/patch`.

## Known issues

- **Empty chats are not returned.** A chat is inserted when created, before any message is sent. Because `getAllChats` uses an INNER JOIN between chats and messages, a chat with no messages is never returned — so a created-but-never-used chat effectively disappears on reload while still occupying a database row.
- **Bare-name vs full-tag model rows can coexist.** Older rows stored bare names (`llama3.1`) while the startup sync stores full tags (`llama3.1:latest`); both can exist until a reconciliation pass is added.
- **`chats.updated_at` isn't refreshed on new messages** (no trigger), so ordering by `updated_at` doesn't reflect recent activity.

## Roadmap / planned work

- **Reconcile the model table against Ollama.** Make the startup sync a true three-way reconciliation: add models Ollama has, update ones in both, and remove database rows for models Ollama no longer has, using the full tag as the single canonical identifier throughout (database, delete, `chats.model`). This resolves the bare-name/full-tag duplication and orphaned rows.
- **User login and accounts** with server-side per-user storage.