from fastapi import FastAPI
from app.db.postgressdb import SessionLocal

app = FastAPI()

@app.get("/")
def root():
    return {"message": "server is running"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/db-test")
def db_test():
    db = SessionLocal()
    try:
        # Simple query to test database connection
        result = db.execute("SELECT 1").fetchone()
        if result and result[0] == 1:
            return {"db_status": "connected"}
        else:
            return {"db_status": "error"}
    except Exception as e:
        return {"db_status": "error", "details": str(e)}
    finally:
        db.close()