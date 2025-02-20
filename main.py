import os
from typing import Optional

import requests
import pydantic
import aiosmtplib
from fastapi import FastAPI, BackgroundTasks
from email.message import EmailMessage
from fastapi.middleware.cors import CORSMiddleware

class ContactForm(pydantic.BaseModel):
    name: str
    company: str
    email: str
    message: str
    turnstile: str = pydantic.Field(alias="cf-turnstile-response", default=None)


class SiteVerifyRequest(pydantic.BaseModel):
    secret: str
    response: str
    remoteip: Optional[str]


class SiteVerifyResponse(pydantic.BaseModel):
    success: bool
    challenge_ts: Optional[str]
    hostname: Optional[str]
    error_codes: list[str] = pydantic.Field(alias="error-codes", default_factory=list)
    action: Optional[str]
    cdata: Optional[str]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins, adjust as needed
    allow_methods=["*"],
    allow_headers=["*"],
)

async def send_email(email, message):
    """Send an email with the given subject and body to the given email address."""
    message = EmailMessage()
    message["From"] = os.environ.get("EMAIL_SENDER")
    message["To"] = email
    message["Subject"] = "New contact form submission"
    message.set_content(message)

    await aiosmtplib.send(
        message,
        hostname=os.environ.get("EMAIL_HOST"),
        port=int(os.environ.get("EMAIL_PORT", 587)),
        username=os.environ.get("EMAIL_USER"),
        password=os.environ.get("EMAIL_PASSWORD"),
    )


@app.get("/")
def read_root():
    return "DaTe contact API"


@app.post("/contact")
def contact(form: ContactForm, background_tasks: BackgroundTasks):
    message = "\n".join([f"{key}: {value}" for key, value in form.model_dump().items() if key not in ["turnstile"]])
    turnstile_key = os.environ.get("TURNSTILE_SECRET_KEY")
    turnstile_req = SiteVerifyRequest(secret=turnstile_key, response=form.turnstile)
    res = requests.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", json=turnstile_req.model_dump())
    if res.status_code != 200:
        return {"error": "Failed to verify turnstile response."}, 400
    turnstile_res = SiteVerifyResponse(**res.json())
    if not turnstile_res.success:
        return {"error": "Failed to verify turnstile response."}, 400
    email = os.environ["EMAIL_ADDRESS"]
    background_tasks.add_task(send_email, email, message)
