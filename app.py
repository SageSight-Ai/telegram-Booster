from fastapi import FastAPI, HTTPException, Form, BackgroundTasks
from telethon import TelegramClient, events
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import InputPeerEmpty
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError, FloodWaitError
from fake_useragent import UserAgent
from tqdm import tqdm
import asyncio
import uvicorn
import random
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# Create a FastAPI app
app = FastAPI()

# Global dictionary to store verification codes for each phone number
verification_codes = {}

@app.post("/start_scraping")
async def start_scraping(
    source_group_username: str = Form(...),
    target_group_username: str = Form(...),
    api_id: int = Form(...),
    api_hash: str = Form(...),
    account_api_ids: str = Form(None),  # Optional, comma-separated API IDs
    account_api_hashes: str = Form(None),  # Optional, comma-separated API hashes
    phone_number: str = Form(...)  # Phone number for verification
):
    try:
        # --- Account Processing (Optional Multi-Account) ---
        if account_api_ids and account_api_hashes:
            account_api_ids = [int(x) for x in account_api_ids.split(",")]
            account_api_hashes = account_api_hashes.split(",")

            if len(account_api_ids) != len(account_api_hashes):
                raise HTTPException(status_code=400, detail="Number of API IDs and API hashes must match.")

            accounts = []
            for i in range(len(account_api_ids)):
                accounts.append({'api_id': account_api_ids[i], 'api_hash': account_api_hashes[i]})

            current_account = random.choice(accounts)
        else:
            # Single-account mode
            current_account = {'api_id': api_id, 'api_hash': api_hash}

        client = TelegramClient('anon', current_account['api_id'], current_account['api_hash'])

        # --- Manual Verification ---
        async def verification_handler(event):
            if event.message.text.startswith("Verification code:"):
                verification_codes[phone_number] = event.message.text.split(":")[1].strip()
                print(f"Verification code received for {phone_number}: {verification_codes[phone_number]}")

        client.add_event_handler(verification_handler, events.NewMessage)

        await client.start()
        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            return {"message": "Verification code requested. Please submit it using /submit_verification_code."}

        # ... (The rest of your scraping logic, which should now be placed AFTER client.start())

    except Exception as e:
        print(f"A general error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/submit_verification_code")
async def submit_verification_code(phone_number: str = Form(...), code: str = Form(...)):
    try:
        client = TelegramClient('anon', api_id, api_hash)  # Create a new client
        await client.start()
        print(f"Attempting to sign in with code: {code}")
        await client.sign_in(phone=phone_number, code=code)
        await client.disconnect()
        return {"message": "Sign-in successful!"}
    except Exception as e:
        print(f"Sign-in error: {e}")
        raise HTTPException(status_code=400, detail=f"Sign-in failed: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
