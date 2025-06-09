from src.bc_user import User, BlockchainNode
from src.text_verificator import Hands

from colorama import Fore, Back
import asyncio
import time, json

import src.estab.block as e_block
import src.estab.transaction as e_tran
import src.estab.verificator as e_ver
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
    nb.make_emission(
        user.node.blockchain,
        user.node.user.address,
        user.node.user.private_key,
        user.node.user.public_key
    )

    nb.phash = user.node.blockchain[-1].hash 
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
    print(f"[>>] MINED block hash: {nb.hash}")
    print(nb.stringify())
    print()
    print()
    return nb

# function: check_new_blocks
# need: it is a cycle to check new blocks, while mining 
#       new block
# returns: returns something only when new block is synced
#          otherwise continues to wait
async def check_new_blocks(user: User, stop_event: asyncio.Event):
    while not stop_event.is_set():
        res = await user.new_block_sync(nolog=True)
        if res:
            block, _ = res
            print(f"[%] confirmed new block: {block.hash}")
            stop_event.set()
            return True
        await asyncio.sleep(1)

async def sync_new_transactions(user: User, stop_event: asyncio.Event):
    while not stop_event.is_set():
        await user.new_transac_sync(nolog=True)
        await asyncio.sleep(0.5)

async def update_nodes_count(user: User, stop_event: asyncio.Event):
    while not stop_event.is_set():
        await user.upd_nodes_num(nolog=True)
        await asyncio.sleep(3)

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
    print(f"[!] work is started")
    last_delta = (time.time() - user.node.blockchain[-1].timestamp) if len(user.node.blockchain) > 0 else 0
    if len(user.node.blockchain) == 0 or (last_delta > 60):
        if (last_delta > 60):
            print(f"[!] local blockchain is old ({(last_delta)}s)")
        print(f"[+] starting full blockchain synchronization")
        await user.full_bc_sync()
    
    print(f"[+] new block synchronization")
    await user.new_block_sync()

    if len(user.node.blockchain) == 0:
        user.node.blockchain.append(e_block.Block.gen_genesis())
    
    if user.node.blockchain[0].hash != "0": # no genesis block
        user.node.blockchain = [e_block.Block.gen_genesis()] + user.node.blockchain

    stop_event = asyncio.Event()

    print(f"[!] starting mining and checking")
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
        if task is check_task:
            hashes = [t.hash for t in user.node.blockchain[-1].transactions] # Checking new block
            newt = []
            
            for t in user.node.transactions:
                if not (t.hash in hashes):
                    newt.append(t)
            user.node.transactions = newt

            print(f"{Fore.YELLOW}[!] new block was calculated by another node{Fore.RESET}")
        if task is mine_task:
            nb = task.result()
            print(f"{Fore.CYAN}[*] new block was calculated firstly{Fore.RESET}")

    
    if nb and isinstance(nb, e_block.Block):
        print(f"[+] new bits were calculated\n\t[{user.node.blockchain[-1].bits} -> {nb.bits}]")
        print(nb.stringify())

        nb.phash = user.node.blockchain[-1].hash
        # Final, third re-check

        await user.propagate_block(nb)

        print(f"[%] new block synchronization check")
        
        start = time.time()
        blocks: list[tuple[e_block.Block, bool]] = []
        while True:
            blocks += await user.new_block_sync(only_check=True, multiple=True, nolog=True, non_agressive=True)
            if (len(blocks) / user.nodes_num >= 0.51) or (time.time() - start > 5): # +1 for self block is not needed
                break
            await asyncio.sleep(0.5)
        
        if len(blocks) == 0:
            print(f"{Fore.MAGENTA}[!] no blocks from other miners{Fore.RESET}")
            user.mined_blocks += 1
            user.node.blockchain.append(nb)

            hashes = [t.hash for t in nb.transactions]
            newt = []
            for t in user.node.transactions:
                if not (t.hash in hashes):
                    newt.append(t)
            user.node.transactions = newt
        else:
            print(f"[^] new blocks!: {len(blocks)}")
            
            for b, nonagr in blocks:
                print(f"   [{"nonagressive!" if nonagr else "classic"}] block: ({b.timestamp}) {b.hash}")

            timestamped = {b.timestamp: (b, nonagr) for b, nonagr in blocks} | {nb.timestamp : (nb, False)}
            earliest = sorted(timestamped)[0]
            print(f"[&] new block: {earliest}/{nb.timestamp} ({Back.BLUE}DELTA: {nb.timestamp - earliest}{Back.RESET})")
            block, nonagr = timestamped[earliest]
            print(f"[{"nonagressive!" if nonagr else "classic"}][{f"{Fore.GREEN}new block was calculated firstly{Fore.RESET}" if block.hash == nb.hash else f"{Fore.RED}new block was calculated by other miner{Fore.RESET}"}]")
            
            if block.hash == nb.hash:
                user.mined_blocks += 1

            if nonagr:
                for t in user.node.blockchain[-1].transactions:
                    user.node.transactions.append(
                        t
                    ) # Re-add transactions

                del user.node.blockchain[-1]
            user.node.blockchain.append(block)

            hashes = [t.hash for t in block.transactions]
            newt = []
            for t in user.node.transactions:
                if not (t.hash in hashes):
                    newt.append(t)
            user.node.transactions = newt
    
    # if user.mined_blocks >= 6:
    #     user.mined_blocks = 0

    #     print(f"{Back.YELLOW}[+] already mined 6 or more blocks{Back.RESET}")
    #     print(f"[*] checking leading blockchain thread")
    #     answers = await user.full_bc_sync(self_verif=False)
    #     if answers:
    #         raw_blockchain, reason = e_ver.NodeVerificator.fsync_verifacation(answers)
            
    #         # If user's thread is not most popular or the longest chain - synchronize blockchain 
    #         if (reason in ["most_popular", "longest chain"]) and (e_block.Block.cook(raw_blockchain[-1]).hash != user.node.blockchain[-1].hash):
    #             print(f"[!] current thread is not the most popular one, re-syncing")
    #             print(f"[!] last hashes does not match: {e_block.Block.cook(raw_blockchain[-1]).hash} != {user.node.blockchain[-1].hash}")
    #             user.node.blockchain = [
    #                 e_block.Block.cook(raw) for raw in raw_blockchain
    #             ]
    #             user.node.transactions = []
    #         else:
    #             print(f"[$] current thread is the most popular/the longest one")
    #     else:
    #         print(f"[!] no answers were got")

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
    

    pemfile = input("Enter path to pem file [quitearno_2] by default: ") or "quitearno2"
    bc_db = input("Enter path to database file [quitearno_bc_2] by default: ") or "quitearno_bc_2"
    verif = input("Enter path to TG session (verificator) [text_verificator_2] by default: ") or "text_verificator_2"

    pemfile = f"./runtime/pems/{pemfile}.pem"
    bc_db = f"./runtime/blockchains/{bc_db}.sqlite3"
    verif = f"./runtime/sessions/{verif}.session"

    config = json.load(open("./configs/tg_app_conf.json"))
    hands = Hands(verif, config["API_HASH"], config["API_ID"])
    user = User(pemfile, "http://192.168.31.100:9001")
    user.set_text_transaction_check(text_transaction_check)

    async def main():
        await hands.connect()
        await user.get_token()
        print(f"token: {user.token}")
        print(f"[*] EST address: {user.node.user.address}")

        load_blockchain(bc_db, user)

        stop_transactions = asyncio.Event()
        asyncio.create_task(answer_pending_reqs(user, stop_transactions))
        asyncio.create_task(sync_new_transactions(user, stop_transactions))
        asyncio.create_task(update_nodes_count(user, stop_transactions))

        while not stop_transactions.is_set():
            await work(user)
            print(f"[+] saving blockchain...")
            dump_blockchain(bc_db, user)
        await hands.disconnect()

    asyncio.run(main())