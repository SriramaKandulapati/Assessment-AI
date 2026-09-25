import os


DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/shortener.db")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
