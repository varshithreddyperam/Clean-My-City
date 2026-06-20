import os
import uvicorn
from dotenv import load_dotenv

# Load env file configurations
load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "3000"))

if __name__ == "__main__":
    print(f"[Launcher] Starting CleanMyCity backend on http://{HOST}:{PORT}")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
