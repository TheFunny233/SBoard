import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "sboard.main:app",
        host=os.getenv("SBOARD_HOST", "0.0.0.0"),
        port=int(os.getenv("SBOARD_PORT", "8000")),
        access_log=False,
    )
