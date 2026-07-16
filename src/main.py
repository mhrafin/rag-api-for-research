from fastapi import Depends, FastAPI
from auth import verify_api_key

app = FastAPI()


@app.get("/")
async def root(key: str =  Depends(verify_api_key)):
    return {"message": "Hello World"}
