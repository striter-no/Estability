import aiogram, json, time
import src.database as db
import uuid
import time
import hashlib

from src.estab.user import User as CrUser
import src.bc_user as api

def fastsha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

class Localizer:
    def __init__(self, config_path: str):
        self.phrases = json.load(open(config_path))
        
    def get(self, phrase: str) -> str:
        return self.phrases[phrase]

class Processor:
    
    def __init__(self, bot: aiogram.Bot, localizer: Localizer, usersdb: db.DataBase, node_ip: str):
        self.localizer = localizer
        self.usersdb = usersdb
        self.bot = bot
        self.temp_usdb = db.DataBase('./runtime/databases/temp_usdb.sqlite3')
        self.node_ip = node_ip

    async def cmd_process(self, text: str, msg: aiogram.types.Message):
        cmd = text[1:].split()[0]
        args = text.split()[1:]

        if cmd == "start":
            await msg.answer(self.localizer.get("start"))
        
        if cmd == "help":
            await msg.answer(self.localizer.get("help"))

        if cmd == "mined":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return

            curr_addr = None
            sha_token = fastsha256(token)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr is None:
                await msg.answer(
                    "Your token is invalid"
                )
                return
            
            user: api.User = api.User(f"./runtime/private_keys/{fastsha256(token)}.pem", self.node_ip)
            msg_id = (await msg.answer(
                "Please wait about 3s"
            )).message_id
            await user.full_bc_sync()
            
            blocks = 0
            emission_earnings = 0
            
            for block in user.node.blockchain[::-1]:
                for transaction in block.transactions:
                    
                    if transaction.output == curr_addr and transaction.ttype == api.e_tran.TRANSACTION_TYPE.emission:
                        emission_earnings += transaction.amount
                        blocks += 1

            await self.bot.delete_message(msg.chat.id, msg_id)
            await msg.answer(
                f"You have:\n*{blocks}* _blocks mined_\n_And you have earned_ *{emission_earnings}* _from it_",
                parse_mode = "Markdown"
            )

        if cmd == "private":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return

            curr_addr = None
            sha_token = fastsha256(token)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr is None:
                await msg.answer(
                    "Your token is invalid"
                )
                return
        
            with open(f"./runtime/private_keys/{fastsha256(token)}.pem") as f:
                key = f.read()

            await msg.answer_document(
                aiogram.types.BufferedInputFile(key.encode(), filename=f"your_private_key.pem"),
                caption = f"It is your private key for `{curr_addr}`",
                parse_mode = "Markdown"
            )

        if cmd == "check":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return

            curr_addr = None
            sha_token = fastsha256(token)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr is None:
                await msg.answer(
                    "Your token is invalid"
                )
                return
            
            if len(args) < 1:
                await msg.answer(
                    "You need to add the transaction's hash to check it. For example:\n`/check 3b322ff620223952c0e3eb995d44f4299591dd0c3bf0562c886e886a0fa80071`",
                    parse_mode = "Markdown"
                )
                return

            t_hash = args[0]
            user: api.User = api.User(f"./runtime/private_keys/{fastsha256(token)}.pem", self.node_ip)
            msg_id = (await msg.answer(
                "Please wait about 3s"
            )).message_id
            await user.full_bc_sync()
            s, t = user.node.check_transaction(t_hash)

            await self.bot.delete_message(msg.chat.id, msg_id)
            await msg.answer(
                f"Transaction __{t_hash[:20]}...__ is {f"verified ({t} times)" if s else "unverified"}",
                parse_mode = "Markdown"
            )

        if cmd == "pay":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return

            curr_addr = None
            sha_token = fastsha256(token)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr is None:
                await msg.answer(
                    "Your token is invalid"
                )
                return
            
            if len(args) < 2:
                await msg.answer(
                    "You need to add the amount of EST to pay to other player and then add an address of the other's wallet. For example:\n`/pay 30EST nZbHA-dLE07LHqBv1MrvcBUlV92wlnoEPsZmLBXf3fY=`",
                    parse_mode = "Markdown"
                )
                return

            try:
                amount = float(args[0].split("EST")[0]) if ("EST" in args[0]) else float(args[0])
            except:
                await msg.answer(
                    f"You need to use a number to provide amount of EST to pay firstly. For example: `30` or `30EST`"
                )
                return

            cuser: api.User = api.User(f"./runtime/private_keys/{fastsha256(token)}.pem", self.node_ip)
            t = api.e_tran.Transaction(
                api.e_tran.TRANSACTION_TYPE.coin,
                cuser.node.user.address,
                args[1],
                time.time(),
                amount = amount,
                pub_key = cuser.node.user.public_key
            )
            t.hash = t.hashme()
            t.signature = t.signme(cuser.node.user.private_key)
            await cuser.propagate_transac(t)

            await msg.answer(
                f"New transaction was send from your address to `{args[1]}`\n\nTransaction hash: `{t.hash}`",
                parse_mode = "Markdown"
            )

        if cmd == "address":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return

            curr_addr = None
            sha_token = fastsha256(token)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr is None:
                await msg.answer(
                    "Your token is invalid"
                )
                return
            
            await msg.answer(
                f"Your address in EST blockchain is: `{curr_addr}`",
                parse_mode = "Markdown"
            )

        if cmd == "balance":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return

            curr_addr = None
            sha_token = fastsha256(token)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr is None:
                await msg.answer(
                    "Your token is invalid"
                )
                return

            user: api.User = api.User(f"./runtime/private_keys/{fastsha256(token)}.pem", self.node_ip)
            msg_id = (await msg.answer(
                "Please wait about 3s"
            )).message_id
            await user.full_bc_sync()
            balance = user.node.check_balance(curr_addr)

            await self.bot.delete_message(msg.chat.id, msg_id)
            await msg.answer(
                f"Your current balance: `{balance}`",
                parse_mode = "Markdown"
            )

        if cmd == "newwallet":
            token = str(uuid.uuid4())
            nuser = CrUser(f"./runtime/private_keys/{fastsha256(token)}.pem")
            self.usersdb.set(nuser.address, fastsha256(token))
            self.temp_usdb.set(msg.from_user.id, token)

            await msg.answer(
                self.localizer.get("newwallet")
                .replace("{{UUID}}", token)
                .replace("{{EST_ADDR}}", nuser.address),
                parse_mode = "Markdown"
            )
        
        if cmd == "obalance":
            token = self.temp_usdb.get(msg.from_user.id)
            
            if token is None:
                await msg.answer(
                    "You don't have your token yet. Make a wallet first: /newwallet or recover previous"
                )
                return
            
            if len(args) < 1:
                await msg.answer(
                    "You need to add an address to check it's ballance. For example:\n`/obalance 25HEX21hhyw2upTjGqMtXHim1xEE3Bn19lgbf70S5ZI=`",
                    parse_mode = "Markdown"
                )
                return

            curr_addr = args[0]
            user: api.User = api.User(f"./runtime/private_keys/{fastsha256(token)}.pem", self.node_ip)
            msg_id = (await msg.answer(
                "Please wait about 3s"
            )).message_id
            await user.full_bc_sync()
            balance = user.node.check_balance(curr_addr)

            await self.bot.delete_message(msg.chat.id, msg_id)
            await msg.answer(
                f"Balance for `{curr_addr}` is: `{balance}`",
                parse_mode = "Markdown"
            )

        if cmd == "recovery":
            
            if len(args) < 1:
                await msg.answer(
                    "You need to add the UUID to recover your wallet. For example:\n`/recover abcde-1234-abde-efg-hijkl123`",
                    parse_mode = "Markdown"
                )
                return

            curr_uuid = args[0]

            curr_addr = None
            sha_token = fastsha256(curr_uuid)
            for addr in self.usersdb.all():
                if self.usersdb.get(addr) == sha_token:
                    curr_addr = addr
            
            if curr_addr:
                nuser = CrUser(f"./runtime/private_keys/{fastsha256(curr_uuid)}.pem")
                self.usersdb.set(nuser.address, fastsha256(curr_uuid))
                self.temp_usdb.set(msg.from_user.id, curr_uuid)

                await msg.answer(
                    f"Wallet was successfully recovered. Your wallet's address: `{curr_addr}`",
                    parse_mode = "Markdown"
                )
            else:
                await msg.answer(
                    f"Wallet was not recovered. Your token is incorrect"
                )

    async def update(self):
        pass

    async def process(self, msg: aiogram.types.Message):
        uid = msg.from_user.id
        self.usersdb.ensure_set(uid, ".")

        text = msg.text or ""
        
        if text[0] == '/':
            await self.cmd_process(text, msg)
            return

        