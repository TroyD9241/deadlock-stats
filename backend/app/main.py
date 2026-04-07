from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.routers import auth, players, matches, heroes
from app.database import engine, Base, get_db

app = FastAPI(title="Deadlock Stats API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(players.router)
app.include_router(matches.router)
app.include_router(heroes.router)


@app.get("/health")
def health_check(db=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB: {e}")
    return {"status": "healthy"}


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
