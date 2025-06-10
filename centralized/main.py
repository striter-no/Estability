import src.database as db
import botprocess as net

import asyncio
import aiogram
import json

tgconf = json.load(open("./cconfigs/dev/tgconf.json"))
usersdb = db.DataBase("./runtime/databases/userdb.sqlite3")
financedb = db.DataBase("./runtime/databases/finance.sqlite3")

localizer = net.Localizer("./cconfigs/speeches.json")
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

    ipconf = json.load(open('./cconfigs/ip_config.json'))

    bot = aiogram.Bot(token = tgconf["API_KEY"])
    process = net.Processor(
        bot, 
        localizer, 
        usersdb, 
        financedb, 
        f"http://{ipconf["serv_ip"]}:{ipconf["serv_port"]}",
        admins=[5243956136]
    )

    await on_start()

    print(f"Start polling")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())