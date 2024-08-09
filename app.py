from fastapi import FastAPI, HTTPException, Form
from telethon import TelegramClient, events
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import InputPeerEmpty
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError
from fake_useragent import UserAgent
from tqdm import tqdm
import asyncio
import uvicorn

# Create a FastAPI app
app = FastAPI()

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

        # --- Automatic Verification with Telethon Events ---
        async def verification_handler(event):
            if event.message.text.startswith("Verification code:"):
                code = event.message.text.split(":")[1].strip()
                await client.sign_in(phone=phone_number, code=code)
                print("Verification successful!")

        client.add_event_handler(verification_handler, events.NewMessage)  # Listen for all new messages

        if not await client.is_user_authorized():
            await client.sign_in(phone=phone_number)
            print("Please enter the verification code you received:")
            # You'll need to manually enter the code here

        await client.start()

        # --- Get the source and target groups ---
        source_group = await client.get_entity(source_group_username)
        target_group = await client.get_entity(target_group_username)

        # --- Scrape Members ---
        participants = []
        offset = 0
        limit = 100  # Number of members to fetch per request

        while True:
            result = await client(GetParticipantsRequest(
                source_group, ChannelParticipantsSearch(''), offset, limit, hash=0
            ))
            participants.extend(result.users)
            offset += len(result.users)

            if not result.users:
                break

            time.sleep(random.randint(1, 3))

        # --- Add Members to Target Group ---
        with tqdm(total=len(participants), desc="Adding Members", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]") as pbar:
            for participant in participants:
                try:
                    # --- User Agent Camouflage ---
                    ua = UserAgent()
                    headers = {'User-Agent': ua.random}
                    await client(InviteToChannelRequest(target_group, [participant]), headers=headers)

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
                    print(f'Error adding {participant.username}: {e}')

                    # If we encounter an error, wait for a longer period
                    delay = random.randint(60, 120)
                    print(f'Waiting for {delay} seconds...')
                    time.sleep(delay)
                    pbar.update(1)  # Update the progress bar even if there's an error

        await client.disconnect()

        return {"message": "Scraping and adding members completed!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
