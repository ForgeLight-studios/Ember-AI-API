# run.py
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("EMBER_PORT", "3100")),
        reload=True,
    )