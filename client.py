from src.bc_user import User, BlockchainNode
from src.text_verificator import Hands

import asyncio
import time, json

import src.estab.block as e_block
import src.estab.transaction as e_tran
import src.database as db

# function: mine_new_block
# need: mines new block
# returns: on success returns new block
async def mine_new_block(user: User, stop_event: asyncio.Event) -> e_block.Block:
    print(f"[+] waiting for transactions")
    while len(user.node.get_mine_transactions()) < e_block.TRANSACTIONS_IN_BLOCK:
        await asyncio.sleep(0.1) # Waiting for transactions
    print(f"[+] aquired transactions...")
    nb = e_block.Block(
        user.node.get_mine_transactions()[:e_block.TRANSACTIONS_IN_BLOCK]
    )

    nb.phash = user.node.blockchain[-1].phash 
    nb.bits = user.node.blockchain[-1].bits
    nb.bits = nb.calcbits(user.node.blockchain)
    nb.merkle = nb.merkle_root()

    def stop_code():
        return stop_event.is_set()

    # stopcode 0 => stop function worked
    # stopcode 1 => hash was found
    print(f"[+] started mining")
    stopcode, delta = nb.mine(stop_code)
    print(f"[+] mined new block") 
    nb.hash = nb.hashme()
    nb.make_emission(
        user.node.blockchain,
        user.node.user.address,
        user.node.user.private_key,
        user.node.user.public_key
    )
    return nb

# function: check_new_blocks
# need: it is a cycle to check new blocks, while mining 
#       new block
# returns: returns something only when new block is synced
#          otherwise continues to wait
async def check_new_blocks(user: User, stop_event: asyncio.Event):
    while not stop_event.is_set():
        block = await user.new_block_sync(nolog=True)
        if block:
            stop_event.set()
            return True
        await asyncio.sleep(2)

async def sync_new_transactions(user: User, stop_event: asyncio.Event):
    while not stop_event.is_set():
        block = await user.new_transac_sync(nolog=True)
        await asyncio.sleep(1)

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

# function: work
# need: 
#   1. Syncs blockchain if node is new
#   2. Syncs new blocks and transactions
#   3. If blockchain is empty generates the genesis block
#   4. Starts to mine a new block, while checking new blocks from other miners
#   5. If new block is mined before other miners, propagation is started
#
# returns: nothing, only user's blockchain changes
async def work(user: User):

    if len(user.node.blockchain) == 0:
        await user.full_bc_sync()
    
    await user.new_block_sync()
    await user.new_transac_sync()

    if len(user.node.blockchain) == 0:
        user.node.blockchain.append(e_block.Block.gen_genesis())
    
    if user.node.blockchain[0].hash != "0": # no genesis block
        user.node.blockchain = [e_block.Block.gen_genesis()] + user.node.blockchain

    stop_event = asyncio.Event()

    mine_task = asyncio.create_task(mine_new_block(user, stop_event))
    check_task = asyncio.create_task(check_new_blocks(user, stop_event))

    done, pending = await asyncio.wait(
        [mine_task, check_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()

    nb = None
    for task in done:
        if task is mine_task:
            nb = task.result()
        if task is check_task:
            hashes = [t.hash for t in user.node.blockchain[-1].transactions] # Checking new block
            newt = []
            
            for t in user.node.transactions:
                if not (t.hash in hashes):
                    newt.append(t)
            user.node.transactions = newt

            print(f"[!] new block was calculated by other node")

    if nb and isinstance(nb, e_block.Block):
        print(f"[+] new bits are calculated\n\t[{user.node.blockchain[-1].bits} -> {nb.bits}]")
        print(nb.stringify())

        block = await user.new_block_sync()
        if not block:
            user.node.blockchain.append(nb)
            await user.propagate_block(nb)

            hashes = [t.hash for t in nb.transactions]
            newt = []
            for t in user.node.transactions:
                if not (t.hash in hashes):
                    newt.append(t)
            user.node.transactions = newt
    
    print(f"[+] new blockchain contains: {len(user.node.blockchain)} blocks:\n\t{'\n\t'.join([b.hash for b in user.node.blockchain[::-1][:5]])}")
    print('-'*50)

async def text_transaction_check(transac: e_tran.Transaction) -> tuple[bool, str]:
    # transac.input => user
    # transac.output => msg_id:chat_id
    # transac.text => text
    # transac.timestamp => timestamp
    
    author_id = int(transac.input)
    msg_id, chat_id = [int(i) for i in transac.output.split(':')]
    s, msg = await hands.check(
        chat_id, msg_id, transac.timestamp, transac.text, author_id
    )
    
    print(f"[!] after checking transaction <{transac.hash}>, result is:\n\t{msg}")

    return s, msg

def dump_blockchain(path: str, user: User):
    bdb = db.DataBase(path)
    for i, block in enumerate(user.node.blockchain):
        bdb.set(i, block.rawme())
    
    print(f"[+] saved {len(user.node.blockchain)} nodes")

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
    
    config = json.load(open("./configs/tg_app_conf.json"))
    hands = Hands("./runtime/sessions/text_verificator.session", config["API_HASH"], config["API_ID"])

    user = User(f"./runtime/pems/quitearno.pem", "http://192.168.31.100:9001")
    user.set_text_transaction_check(text_transaction_check)

    async def main():
        await hands.connect()
        await user.get_token()
        print(f"token: {user.token}")

        load_blockchain("./runtime/blockchains/quitearno_bc.sqllite3", user)

        stop_transactions = asyncio.Event()
        asyncio.create_task(answer_pending_reqs(user, stop_transactions))
        asyncio.create_task(sync_new_transactions(user, stop_transactions))

        while not stop_transactions.is_set():
            await work(user)
            dump_blockchain("./runtime/blockchains/quitearno_bc.sqllite3", user)
        await hands.disconnect()

    asyncio.run(main())