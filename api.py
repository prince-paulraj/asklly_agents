from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from db import SessionLocal
from time import sleep
import uuid
import time
import json, logging

import asyncio
from main import initialize_system
from schemas import QueryRequest as Query
from interaction import Interaction
from session_manager import session_manager 

api = FastAPI()
interaction_instance: Interaction = None
interaction_lock = asyncio.Lock()
log =  logging.getLogger(__name__)
logging.basicConfig(filename="main.log",level=logging.INFO)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

api.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.get("/")
async def hello():
    return "Agent is working"

@api.post("/agent")
async def agent(query: Query, db: Session = Depends(get_db)):
    async def stream():
        cid = query.cid if query.cid else str(uuid.uuid5(uuid.NAMESPACE_DNS, str(query.uid) + str(time.time())))
        interaction_instance = await session_manager.get_session(cid)
        start = time.time()
        interaction_instance.set_query(query.query, query.bot_key, db)
        print(f"Starting the questioning: {query.query}")
        await interaction_instance.think(query.uid, query.org)
        yield json.dumps({"status":"RUNNING"})
        while True:
            await asyncio.sleep(1)
            if interaction_instance.last_answer:
                json_dump = {"status":"SUCCESS", "answer": interaction_instance.last_answer, "thinking": interaction_instance.last_reasoning, "end": int(time.time()) - int(start)}
                if interaction_instance.last_browser_search:
                    json_dump["search"] = interaction_instance.last_browser_search
                if interaction_instance.browser_sources:
                    json_dump["sources"] = interaction_instance.browser_sources
                yield json.dumps(json_dump)
                print("Answer Generated")
                print("Reasoning: ",interaction_instance.last_reasoning)
                print("Answer: ",interaction_instance.last_answer)
                await session_manager.cleanup_sessions()
                break
            print("Generating Answer....")
    return StreamingResponse(stream())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:api", host="0.0.0.0", port=8844, workers=2)