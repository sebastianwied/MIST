from fastapi import FastAPI
from pydantic import BaseModel

from mist_agent.respond import handle_text

app = FastAPI()

class Msg(BaseModel):
    text: str

@app.post("/message")
def message(msg: Msg):
    reply = handle_text(msg.text, source="app")
    return {"reply": reply}
