import telethon as th
import asyncio
import logging
import uuid

logging.basicConfig(level=logging.ERROR)

class Hands:
    def __init__(
            self,
            session: str,
            api_hash: str,
            api_id: int,
            ignore_me: bool = True
    ):
        self.loop = asyncio.get_event_loop()
        self.client = th.TelegramClient(
            session=session,
            api_hash=api_hash,
            api_id=api_id
        )
        self.client.add_event_handler(self.__new_msg_handler, th.events.NewMessage)
        self.me: th.types.User = None
        
        self.catch_space = []
        self.catch_targets = []
        self.ignore_me = ignore_me

    async def __new_msg_handler(self, event: th.events.newmessage.NewMessage.Event):
        if not (event.chat_id in self.catch_targets): return
        msg: th.types.Message = event.message
        text = msg.message

        if not text: return
        if not hasattr(msg.from_id, "user_id"): return
        
        if self.ignore_me and msg.from_id.user_id == self.me.id: return 
        self.catch_space.append((event.chat_id, text, msg.from_id.user_id, msg))

    async def __send_msg(self, chatid: int, msg_text: str):
        await self.client.send_message(
            chatid, msg_text
        )

    def new_target(self, chatid: int):
        self.catch_targets.append(chatid)

    def rem_target(self, chatid: int):
        del self.catch_targets[
            self.catch_targets.index(chatid)
        ]

    async def reach_out(self, chatid: int, msg: str):
        await self.__send_msg(
            chatid,
            msg
        )
    
    def catch_new(self) -> tuple[int, str, int, th.types.Message] | None:
        if len(self.catch_space) != 0:
            t = self.catch_space[0]
            del self.catch_space[0]

            return t
        return None
    
    def catch_by_filter(self, filter) -> tuple[int, str, int, th.types.Message] | None:
        for i in range(len(self.catch_space)):
            if filter(self.catch_space[i]):
                t = self.catch_space[i]
                del self.catch_space[i]

                return t

        return None

    def run(self, updater):
        async def main():
            await self.client.start()
            await self.client.connect()

            self.me = await self.client.get_me()

            await updater.start()
            while updater.up():
                await self.client(th.functions.updates.GetStateRequest())
                await updater.work()
        
        asyncio.run(main())