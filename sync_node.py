from src.bc_user import User, BlockchainNode
from src.text_verificator import Hands

import asyncio
import time, json

import src.estab.block as e_block
import src.estab.transaction as e_tran
import src.database as db

def elapsed_time(start) -> tuple[tuple[int, int, int, int, float], float]:
    elapsed = time.time() - start
    days = int(elapsed // 86400)
    hours = int((elapsed % 86400) // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    milliseconds = (elapsed - int(elapsed)) * 1000 

    return (days, hours, minutes, seconds, milliseconds), elapsed

async def answer_pending_reqs(user: User, stop_event: asyncio.Event):
    cache_hashes = []
    while not stop_event.is_set():
        preq = await user.check_pending_req(True) # jupdate
        if preq and not (preq.uuid in cache_hashes):
            if preq.type == "sync" and preq.entity == "bc": # Syncing blockchain
                cache_hashes.append(preq.uuid)
                await user.send_answer(
                    preq.uuid, [cooked.rawme() for cooked in user.node.blockchain]
                )
            # Syncing new blocks and transactions
            # is server-side
        await asyncio.sleep(2)

def dump_blockchain(path: str, user: User):
    bdb = db.DataBase(path)
    bdb.batch_set([(i, block.rawme()) for i, block in enumerate(user.node.blockchain)])
    
    print(f"[+] saved {len(user.node.blockchain)} blocks")

def load_blockchain(path: str, user: User):
    bdb = db.DataBase(path)
    if len(bdb.all()) == 0:
        print(f"[+] blockchain's database is empty")
        return
    
    keys = sorted(bdb.all())
    for k in keys:
        user.node.blockchain.append(
            e_block.Block.cook(bdb.get(k))
        )
    
    print(f"[+] restored {len(keys)} blocks")

if __name__ == "__main__":
    # user = User(f"./runtime/pems/user_{str(round(time.time()*100))[::-1][:5]}.pem", "http://127.0.0.1:5000")
    

    pemfile = input("Enter path to pem file [quitearno] by default: ") or "quitearno"
    bc_db = input("Enter path to database file [quitearno_bc] by default: ") or "quitearno_bc"

    pemfile = f"./runtime/pems/{pemfile}.pem"
    bc_db = f"./runtime/blockchains/{bc_db}.sqlite3"

    config = json.load(open("./configs/tg_app_conf.json"))
    user = User(pemfile, "http://192.168.31.100:9001")

    async def main():
        start = time.time()
        await user.get_token()
        print(f"token: {user.token}")
        print(f"[*] EST address: {user.node.user.address}")

        load_blockchain(bc_db, user)

        stop_transactions = asyncio.Event()
        asyncio.create_task(answer_pending_reqs(user, stop_transactions))

        while not stop_transactions.is_set():
            await user.full_bc_sync()
            
            (d, h, m, s, ms), alls = elapsed_time(start)            
            print(f"[+] node is up ({d}d {h}h {m}m ({s} seconds))")
            dump_blockchain(bc_db, user)

            await asyncio.sleep(10) # To not to flood

    asyncio.run(main())
