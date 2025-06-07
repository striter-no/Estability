import client as api
from src.hands import Hands
import json, telethon as th, time

TARGET_CHAT = -1001236072132

class Updater:
    def __init__(self, main_pem: str, test_pem: str, hands: Hands, node_ip: str):
        self.hands: Hands = hands
        self.node_ip = node_ip
        
        self.verificator_hands: api.Hands = api.Hands(
            "./runtime/sessions/transac_verif.session", config["API_HASH"], config["API_ID"]
        )

        self.user = api.User(main_pem, node_ip)
        self.test_user = api.User(test_pem, node_ip)
        
        self.test_user.set_text_transaction_check(api.text_transaction_check)
        self.user.set_text_transaction_check(api.text_transaction_check)
        self.curr_user = "user"

    def filter(self, msg: tuple[int, str, int, th.types.Message]):
        chatid, text, authorid, tmsg = msg
        return chatid == TARGET_CHAT and text[0] == '!'

    def up(self):
        return True
    
    async def start(self):
        await self.verificator_hands.connect()

    def current_user(self):
        match self.curr_user:
            case "user": return self.user
            case "test": return self.test_user
        return self.test_user

    async def work(self):
        rq = self.hands.catch_by_filter(self.filter)
        if rq:
            chatid, text, authorid, tmsg = rq
            spl_t = text.split()

            if text == "!swap":
                match self.curr_user:
                    case "user": self.curr_user = "test"
                    case "test": self.curr_user = "user"

                await self.hands.reach_out(chatid, f"Current working EST address: `{self.current_user().node.user.address}`")

            if text == "!help":
                await self.hands.reach_out(chatid, "**Estability [chain] v0.0.3**\n__Protocol version: v1__\n\nThe system is designed to sign text messages on the blockchain. To mine new blocks contact your nearest Estability employee. \n\nApproximate time to sign a message is 4 minutes (2 minutes to mine a block and 2 minutes for the next block, for more confidence).\n\nTo use the system from telegram, you can reply to the message with the `!sign` command to be signed and it will be sent to the blockchain as a transaction.")

            if text == "!addr":
                await self.hands.reach_out(chatid, f"Node EST address: `{self.current_user().node.user.address}`")

            if spl_t[0] == "!pay":
                if len(spl_t) < 2:
                    await self.hands.reach_out(chatid, "__You need an address and amount to pay EST:__ `!pay 54EST 12bd2e...`\nYou can skip `EST` part")
                    return
                
                amount = float(spl_t[1].split("EST")[0]) if ("EST" in spl_t[1]) else float(spl_t[1])
                cuser = self.current_user()
                t = api.e_tran.Transaction(
                    api.e_tran.TRANSACTION_TYPE.coin,
                    cuser.node.user.address,
                    spl_t[2],
                    time.time(),
                    amount = amount,
                    pub_key = cuser.node.user.public_key
                )
                t.hash = t.hashme()
                await self.current_user().propagate_transac(t)
                print(t.hash)
                await self.hands.reach_out(chatid, f"`{t.hash}`")
                # await self.hands.client.delete_messages(chatid, tmsg.id)

            if spl_t[0] == "!bal":
                if len(spl_t) == 1:
                    await self.hands.reach_out(chatid, "__You need an address to check a balance:__ `!bal 12bd2e...`")
                    return
                address = spl_t[1]

                await self.current_user().full_bc_sync()

                balance = self.current_user().node.check_balance(address)
                await self.hands.reach_out(chatid, f"__Balance for <{address[:10]}...> is:__ `{balance}`")

            if text == "!sign":
                if tmsg.reply_to is None:
                    await self.hands.reach_out(chatid, "__Message can not be signed. Reply is empty__")
                    return

                repl_msg = await self.hands.client.get_messages(chatid, ids=tmsg.reply_to.reply_to_msg_id)
                if not repl_msg.message:
                    await self.hands.reach_out(chatid, "__Message can not be signed. You need to reply to a normal text message__")
                    return

                if len(repl_msg.message) == 0:
                    await self.hands.reach_out(chatid, "__Message can not be signed. Text is empty__")
                    return

                t = api.e_tran.Transaction(
                    api.e_tran.TRANSACTION_TYPE.text,
                    str(repl_msg.from_id.user_id),
                    f"{repl_msg.id}:{chatid}",
                    repl_msg.date.timestamp(),
                    repl_msg.message
                )
                t.hash = t.hashme()

                await self.current_user().propagate_transac(t)
                # await self.hands.reach_out(chatid, f"`{t.hash}`")
                
                if authorid == self.hands.me.id:
                    await self.hands.client.delete_messages(chatid, tmsg.id)
                    await self.hands.client.send_message(
                        chatid, f"__Transaction created__ ({chatid}): \n`{t.hash}`"
                    )
                else:
                    await self.hands.client.send_message(
                        chatid, f"__Transaction created__ ({chatid}): \n`{t.hash}`", reply_to=tmsg.id
                    )

if __name__ == "__main__":
    config = json.load(open("./configs/tg_app_conf.json"))
    hands = Hands(
        "./runtime/sessions/transac_creator.session",
        api_hash=config["API_HASH"],
        api_id=config["API_ID"],
        ignore_me=False
    )

    print("Starting")
    hands.new_target(TARGET_CHAT)
    hands.run(Updater(
        "./runtime/pems/quitearno.pem",
        "./runtime/pems/test.pem",
        hands, 
        "http://192.168.31.100:9001"
    ))