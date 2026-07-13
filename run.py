# run.py
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="localhost",
        port=int(os.getenv("EMBER_PORT", "3100")),
        reload=True,
    )