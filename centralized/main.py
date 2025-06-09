import src.database as db
import botprocess as net

import asyncio
import aiogram
import json

tgconf = json.load(open("./configs/dev/tgconf.json"))
usersdb = db.DataBase("./runtime/databases/userdb.sqlite3")

localizer = net.Localizer("./configs/speeches.json")
dp = aiogram.Dispatcher()

async def update_state():
    while True:
        await process.update()
        await asyncio.sleep(1)

async def on_start():
    asyncio.create_task(update_state())

@dp.message()
async def handle_message(message: aiogram.types.Message) -> None:
    if not message.md_text: return
    await process.process(message)

async def main():
    global bot
    global process

    bot = aiogram.Bot(token = tgconf["API_KEY"])
    process = net.Processor(bot, localizer, usersdb, "http://192.168.31.100:9001")

    await on_start()

    print(f"Start polling")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())