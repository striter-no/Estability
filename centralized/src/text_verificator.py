import telethon as th
import asyncio
import logging

logging.basicConfig(level=logging.ERROR)

class Hands:
    def __init__(
            self,
            session: str,
            api_hash: str,
            api_id: int
    ):
        self.client = th.TelegramClient(
            session=session,
            api_hash=api_hash,
            api_id=api_id
        )
        self.me: th.types.User = None
    
    async def find_user_in_chat(self, chat_id, user_id):
        try:
            # Получаем всех участников чата
            participants = await self.client.get_participants(chat_id)
            # Ищем пользователя с указанным ID
            for participant in participants:
                if participant.id == user_id:
                    return participant  # Возвращаем найденного пользователя
            return None  # Пользователь не найден
        except Exception as ex:
            print(f"Ошибка при получении участников: {ex}")
            return None

    async def check(
            self, 
            chatid: int, 
            msgid: int, 
            timestamp: float,
            text: str,
            author: int
    ) -> tuple[bool, str]:
        try:
            _ = await self.client.get_input_entity(author)
        except:
            await self.find_user_in_chat(chatid, author)
            

        # 1. Check author existence
        try:
            eauthor = await self.client.get_input_entity(author)
        except Exception as ex:
            return False, f"Author [{author}] was not found ({ex})"
        # 2. Check chat existence
        try:
            echat = await self.client.get_input_entity(chatid)
        except Exception as ex:
            return False, f"Chat [{chatid}] was not found ({ex})"
        # 3. Check message existence
        for i in range(3):
            try:
                msg: th.types.Message = await self.client.get_messages(echat, ids=msgid)
                break
            except Exception as ex:
                print(f"[!] Message [{msgid}] cannot be confimed ({i+1}/3): {ex}")
                if i == 2:
                    return False, f"Message [{msgid}] was not found ({ex})"
                await asyncio.sleep(0.5)
                    
        # 4. Check message timestamp (+- 15m)
        try:
            if abs(msg.date.timestamp() - timestamp) > (60 * 15):
                return False, f"Message [{msgid}] is too old ({abs(msg.date.timestamp() - timestamp)})"
        except Exception as ex:
            return False, f"Message's [{msgid}] timestamp is undefined ({ex})"
        # 5. Check message text
        if len(msg.message) == 0:
            return False, f"Message [{msgid}] has no text"
        
        if msg.message != text:
            return False, f"Message [{msgid}] has text mismatch"
        
        return True, "Ok"

    async def connect(self):
        await self.client.start()
        await self.client.connect()
        self.me = await self.client.get_me()
    
    async def disconnect(self):
        await self.client.disconnect()
