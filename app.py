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
import time
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# Create a FastAPI app
app = FastAPI()

# Global dictionary to store verification codes for each phone number
verification_codes = {}

# Function to perform the scraping and adding in the background
async def scrape_and_add(client, source_group_username, target_group_username, accounts):
    # --- Get the source and target groups ---
    try:
        source_group = await client.get_entity(source_group_username)
        target_group = await client.get_entity(target_group_username)
    except ValueError as e:
        print(f"Error getting groups: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid group username: {e}")
    except Exception as e:
        print(f"Unexpected error getting groups: {e}")
        raise HTTPException(status_code=500, detail="Failed to get groups.")

    print("Groups retrieved")

    # --- Scrape Members ---
    participants = []
    offset = 0
    limit = 100  # Number of members to fetch per request

    while True:
        try:
            result = await client(GetParticipantsRequest(
                source_group, ChannelParticipantsSearch(''), offset, limit, hash=0
            ))
            participants.extend(result.users)
            offset += len(result.users)

            if not result.users:
                break

            time.sleep(random.randint(1, 3))
        except FloodWaitError as e:
            print(f"Flood wait error: {e}")
            wait_time = e.seconds
            print(f"Waiting for {wait_time} seconds...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"Error scraping members: {e}")
            raise HTTPException(status_code=500, detail="Failed to scrape members.")

    print(f"Found {len(participants)} members in {source_group_username}")

    # --- Add Members to Target Group ---
    added_count = 0
    with tqdm(total=len(participants), desc="Adding Members", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]") as pbar:
        for participant in participants:
            try:
                # --- User Agent Camouflage ---
                ua = UserAgent()
                headers = {'User-Agent': ua.random}
                await client(InviteToChannelRequest(target_group, [participant]), headers=headers)
                added_count += 1
                print(f'Added {participant.username} to {target_group_username}')

                # --- Longer Delays ---
                delay = random.randint(30, 120)  # Increased delay range
                print(f'Waiting for {delay} seconds...')
                time.sleep(delay)

                pbar.update(1)  # Update the progress bar

            except PeerFloodError:
                print('Oh no! Telegram is angry! Switching accounts...')
                # --- Account Rotation --- (If multi-account is enabled)
                if accounts:
                    current_account = random.choice(accounts)
                    client.disconnect()
                    client = TelegramClient('anon', current_account['api_id'], current_account['api_hash'])
                    await client.start()
                else:
                    raise  # Re-raise the error if in single-account mode

            except UserPrivacyRestrictedError:
                print(f'Uh oh, {participant.username} has privacy settings enabled. Skipping...')
                pbar.update(1)  # Update the progress bar even if skipping

            except Exception as e:
                print(f'Error adding {participant.username} to group {target_group_username}: {e}')

                # If we encounter an error, wait for a longer period
                delay = random.randint(60, 120)
                print(f'Waiting for {delay} seconds...')
                time.sleep(delay)
                pbar.update(1)  # Update the progress bar even if there's an error

    await client.disconnect()
    print(f"Scraping and adding members completed! Added {added_count} members.")

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
    global verification_code
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
            accounts = None  # No account rotation in single-account mode

        client = TelegramClient('anon', current_account['api_id'], current_account['api_hash'])

        # --- Manual Verification ---
        async def verification_handler(event):
            global verification_code
            if event.message.text.startswith("Verification code:"):
                verification_codes[phone_number] = event.message.text.split(":")[1].strip()
                print(f"Verification code received for {phone_number}: {verification_codes[phone_number]}")

        client.add_event_handler(verification_handler, events.NewMessage)

        await client.start()

        if not await client.is_user_authorized():
            await client.send_code_request(phone_number)
            return {"message": "Verification code requested. Please submit it using the form below."}
        else:
            # --- Start the scraping in the background --- ONLY if authorized!
            asyncio.create_task(scrape_and_add(client, source_group_username, target_group_username, accounts))
            return {"message": "Already authorized! Scraping process started in the background."}

    except Exception as e:
        print(f"A general error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/submit_verification_code")
async def submit_verification_code(phone_number: str = Form(...), code: str = Form(...)):
    global verification_code
    try:
        # Use the correct API ID and hash here
        client = TelegramClient('anon', api_id, api_hash)  # Create a new client
        await client.start()
        await client.sign_in(phone=phone_number, code=code)
        verification_code = code  # Update the global verification code
        await client.disconnect()
        return {"message": "Sign-in successful! You can now close this window."}
    except Exception as e:
        print(f"Sign-in error: {e}")
        raise HTTPException(status_code=400, detail=f"Sign-in failed: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
