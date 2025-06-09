import telethon as th, json as jn, logging, asyncio
import src.database as db
logging.basicConfig(level=logging.ERROR)

from src.estab.user import User as CrUser
import src.bc_user as api

config = jn.load(open("./configs/tg_app_conf.json"))

client = th.TelegramClient(
    session="./runtime/sessions/mass_sign.session",
    api_hash=config["API_HASH"],
    api_id=config["API_ID"]
)

async def main():
    await client.start()
    await client.connect()

    user: api.User = api.User('./runtime/pems/quitearno.pem', "http://192.168.31.100:9001")
    target_chat_id = input(f"Enter chat to mass-sign > ").strip() or "-1001236072132"
    target_chat = await client.get_entity(int(target_chat_id) if (target_chat_id.isdigit() or (target_chat_id[0] == '-' and target_chat_id[1:].isdigit())) else target_chat_id)

    try:
        with open("./runtime/mass_sign_journal.txt") as f:
            ofst = int(f.read())
    except:
        ofst = 0

    i = 0
    async for msg in client.iter_messages(target_chat, offset_id=ofst):
        msg: th.types.Message = msg

        if msg.message and len(msg.message) > 0 and hasattr(msg.from_id, "user_id"):
            t = api.e_tran.Transaction(
                api.e_tran.TRANSACTION_TYPE.text,
                str(msg.from_id.user_id),
                f"{msg.id}:-100{target_chat.id}",
                msg.date.timestamp(),
                msg.message
            )
            
            t.hash = t.hashme()
            with open("./runtime/mass_sign_journal.txt", "w") as f:
                f.write(f"{msg.id}")
            await user.propagate_transac(t)

            # if i % 5 == 0 and i != 0:
            #     input(f"> ")
            i += 1

        await asyncio.sleep(3)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
