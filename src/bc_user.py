from typing import Callable

import asyncio
import aiohttp
import time, uuid

import src.estab.block as e_block
import src.estab.transaction as e_tran
import src.estab.verificator as e_ver
import src.estab.user as e_user

TIME_DIFF = 30

class Request:
    def __init__(self, type: str, entity: str, body: str, vuuid: str, timestamp: float):
        self.type = type
        self.entity = entity
        self.body = body

        self.uuid = vuuid
        self.timestamp = timestamp

class BlockchainNode:
    def __init__(self, pem_key: str):
        self.user = e_user.User(pem_key)
        
        self.transactions: list[e_tran.Transaction] = []
        self.blockchain: list[e_block.Block] = []

    def check_transaction(self, transac_hash: str) -> tuple[bool, int]:
        approvoes = 0
        for block in self.blockchain[::-1]:
            if transac_hash in [t.hash for t in block.transactions]:
                return True, approvoes

            approvoes += 1
        
        return False, 0

    def check_balance(self, address: str) -> float:
        input_balance = 0
        output_balance = 0
        print(f"[!] blockchain len: {len(self.blockchain)}", flush=True)
        for block in self.blockchain[::-1]:
            for transaction in block.transactions:
                
                if transaction.output == address:# and self.check_transaction(transaction.hash)[1] >= 6:
                    input_balance += transaction.amount
                if transaction.input == address:# and self.check_transaction(transaction.hash)[1] >= 6:
                    output_balance += transaction.amount

        return input_balance - output_balance

    def get_mine_transactions(self):
        dct = {}
        for t in self.transactions:
            dct[t.timestamp] = t

        return [dct[t] for t in sorted(dct)[::-1]]
    
class User:
    def __init__(self, pem_key: str, node_ip: str):
        self.node = BlockchainNode(pem_key)
        self.const_node = node_ip
        self.token = ""
        self.text_transac_check = None
        self.new_block_hashes = []
        self.propagated_block_hashes = []
        self.nodes_num = 0
        self.mined_blocks = 0

    async def upd_nodes_num(self, nolog=False):
        self.nodes_num = await self.num_of_nodes(nolog=nolog)

    def set_text_transaction_check(self, checker: Callable):
        self.text_transac_check = checker

    async def check_answer(self, req: aiohttp.ClientResponse) -> tuple[bool, str]:
        try:
            data = await req.json()
            if data["status"] != "ok":
                return False, f"{data['status']}: {data['reason']}"
            
            return True, "ok"

        except:
            return False, "Internal Server Error: Invalid JSON"

    async def send_answer(self, req_uuid: str, answer_body: str | dict | list) -> tuple[bool, str]:
        print(f"[+] sending answer to <{req_uuid}>: {str(answer_body).replace('\\n', ' ')[:50]}", flush=True)
        max_retries = 5
        retry_delay = 5  # seconds
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/answer", json={
                        "token": self.token,
                        "uuid": req_uuid,
                        "body": answer_body
                    }) as req:
                        return await self.check_answer(req)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise
        return False, "Network failure"

    async def check_pending_req(self, nolog = False) -> Request | None:
        if not nolog: print(f"[+] checking pending requests", flush=True)
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/jupdate", json={
                        "token": self.token
                    }) as req:
                        status, msg = await self.check_answer(req)

                        if status:
                            data = await req.json()
                            if not nolog: print(f"[>] request got:\n\t{data['type']}-{data['entity']}-{data['uuid']}-{data['timestamp']}-{str(data['body']).replace('\\n', ' ')[:50]}", flush=True)
                            return Request(data["type"], data["entity"], data["body"], data["uuid"], data["timestamp"])
                        elif not msg.startswith("warning"):
                            print(f"[!] couldnt get pending requests", flush=True)
                            raise RuntimeError(f"Couldn't get pending request: {msg}")
                        else:
                            if not nolog: print(f"[$] no pending requests are available", flush=True)
                            return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def new_block_sync(self, nolog = False, only_check = False, multiple = False, non_agressive = False, no_phash_clone=False) -> tuple[e_block.Block, bool] | list[tuple[e_block.Block, bool]] | tuple[list[tuple[e_block.Block, bool]], list[tuple[e_block.Block, bool]]] | None:
        if not nolog: print(f"[+] new block syncing...", flush=True)
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/update", json={
                        "token": self.token,
                        "target": "newblock"
                    }) as req:
                        status, msg = await self.check_answer(req)
                        
                        answers: list[e_block.Block] = []
                        if status:
                            data = await req.json()
                            rec_uuid = data["uuid"]
                            # if rec_uuid in self.propagated_block_hashes:
                            #     if not nolog: print(f"[<>] skiping self-propagated block", flush=True)
                            #     return
                            i = 0
                            if not nolog: print(f"[*] update request successeded, getting answer", flush=True)

                            while True:
                                async with session.get(f"{self.const_node}/check", json={
                                    "token": self.token,
                                    "uuid": rec_uuid
                                }) as req_check:
                                    status, msg = await self.check_answer(req_check)
                                    multiple_blocks = []
                                    no_phash_clones = []
                                    if status:
                                        data = await req_check.json()
                                        if not nolog: print(f"[>] new blocks are got ({len(data["answers"])})", flush=True)
                                        answers = [e_block.Block.cook(b) for b in data["answers"]]
                                        # Check for duplicates
                                        all_cached = True
                                        for b in answers:
                                            # print(f"... [*] looking at <{b.hash}>", flush=True)
                                            if b.hash in self.new_block_hashes or b.hashme() in [oldb.hash for oldb in self.node.blockchain]:
                                                continue
                                            
                                            all_cached = False

                                            self.new_block_hashes.append(b.hash)
                                            
                                            print(f"--> [*] checking <{b.hash}>", flush=True)

                                            s, msg = await b.checkme(self.node, self.node.blockchain[-1], self.text_transac_check, phash_agrs_check=non_agressive, pre_prev_block= self.node.blockchain[-2] if non_agressive else None, ignore_phash = no_phash_clone)
                                            non_agressive_ok = msg == "non_agressive_ok"
                                            all_but_phash = msg == "ignored_phash"

                                            print(f"[(!)] block {b.hash} is {"OK" if s else "DISMISSED"}", flush=True)


                                            if non_agressive_ok:
                                                print(f"[!] NON-AGRESSIVE block: {b.hash}", flush=True)

                                            if not s:
                                                if not (b.hash in [oldb.hash for oldb in self.node.blockchain]):
                                                    print(f"[!] block <{b.hash}> is uncomfired: {msg}", flush=True)
                                                # else:
                                                #     print(f"[!] block was in blockchain but failed: {msg}", flush=True)
                                                continue # Skip malicious ones
                                            if b.hash in [oldb.hash for oldb in self.node.blockchain]:
                                                print(f"[!] block <{b.hash}> was in blockchain", flush=True)
                                                continue

                                            # Aim especially for new ones (TIME_DIFF s difference)
                                            # If it only check, than increase difference
                                            
                                            if (abs(time.time() - b.timestamp) <= TIME_DIFF):
                                                if not only_check: self.node.blockchain.append(b)
                                                # if not nolog: 
                                                print(f"[!] got new block: <{b.hash}>", flush=True)
                                                if not multiple: return b, non_agressive_ok
                                                elif multiple and all_but_phash: no_phash_clones.append((b, non_agressive_ok))
                                                elif multiple and not all_but_phash: multiple_blocks.append((b, non_agressive_ok))
                                            elif abs(time.time() - b.timestamp) > TIME_DIFF:
                                                print(f"[!!] block <{b.hash}> is too old ({abs(time.time() - b.timestamp)} delta)", flush=True)
                                        # Done
                                        if multiple and not no_phash_clone:
                                            return multiple_blocks
                                        if multiple and no_phash_clone:
                                            return multiple_blocks, no_phash_clones

                                        if not nolog: 
                                            if not all_cached and len(answers) != 0:
                                                print(f"[!] no new blocks are correct", flush=True)
                                            if len(answers) == 0:
                                                print("[!] no new blocks was obtained (no answers)", flush=True)
                                            if len(answers) != 0 and all_cached:
                                                print(f"[!] all new blocks are cached", flush=True)
                                        return None
                                    elif i >= 20: # 2 seconds are gone
                                        if not nolog: print(f"[!] response time out", flush=True)
                                        return
                                    elif not status and not msg.startswith("warning"):
                                        if not nolog: print(f"[!] couldn't get new blocks: {msg}", flush=True)
                                        return

                                    await asyncio.sleep(0.1)
                                    i += 1
                        else:
                            if not nolog: print(f"[!] couldn't get new blocks:\n\t{msg}", flush=True)
                            raise RuntimeError(f"Couldn't get new blocks: {msg}")
                break
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def new_transac_sync(self, nolog = False):
        if not nolog: print(f"[+] new transactions sync was called", flush=True)
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/update", json={
                        "token": self.token,
                        "target": "newtransac"
                    }) as req:
                        status, msg = await self.check_answer(req)
                        answers: list[e_tran.Transaction] = []

                        if status:
                            data = await req.json()
                            rec_uuid = data["uuid"]
                            i = 0
                            if not nolog: print(f"[+] got uuid for newtransac request: <{rec_uuid}>", flush=True)

                            while True:
                                async with session.get(f"{self.const_node}/check", json={
                                    "token": self.token,
                                    "uuid": rec_uuid
                                }) as req_check:
                                    status, msg = await self.check_answer(req_check)
                                    
                                    if status:
                                        data = await req_check.json()
                                        answers = [e_tran.Transaction.cook(tr) for tr in data["answers"]]

                                        # Check for duplicates
                                        for t in answers:
                                            if t.hash in [oldt.hash for oldt in self.node.transactions]:
                                                continue # Skip duplicates
                                            
                                            if self.node.check_transaction(t.hash)[0]:
                                                continue # Skip duplicates

                                            if not (await t.checkme(self.node, len(self.node.blockchain), self.text_transac_check)):
                                                continue # Skip malicious ones

                                            self.node.transactions.append(t)
                                        return
                                        # Done
                                    elif i >= 20: # 2 seconds are gone
                                        if not nolog: print(f"[!] response time out", flush=True)
                                        return
                                    elif not status and not msg.startswith("warning"):
                                        if not nolog: print(f"[!] couldn't get transaction: {msg}", flush=True)
                                        return

                                    await asyncio.sleep(0.1)
                                    i += 1
                        else:
                            if not nolog: print(f"[!] couldn't get new transactions:\n\t{msg}", flush=True)
                            raise RuntimeError(f"Couldn't get new transactions: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def full_bc_sync(self, self_verif = True):
        print(f"[+] starting full BC sync", flush=True)
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/update", json={
                        "target": "blockchain",
                        "token": self.token
                    }) as req:
                        status, msg = await self.check_answer(req)
                        answers = []

                        if status:
                            data = await req.json()
                            req_uuid = data["uuid"]
                            print(f"[*] request successeded: <{req_uuid}>", flush=True)
                            await asyncio.sleep(3) # Wait for the answer
                            i = 0

                            while True:
                                async with session.get(f"{self.const_node}/check", json={
                                    "token": self.token,
                                    "uuid": req_uuid
                                }) as req_check:
                                    status, msg = await self.check_answer(req_check)

                                    if status:
                                        answers = await req_check.json()
                                        answers = answers["answers"]
                                        print(f"[>] answers got: {str(answers).replace('\\n', ' ')[:50]}", flush=True)
                                        break
                                    elif not msg.startswith("warning"):
                                        print(f"[!] couldn't full sync bc and check answers:\n\t{msg}", flush=True)
                                        raise RuntimeError(f"Couldn't full sync bc and check answers: {msg}")
                                    elif i > 20: # 2 seconds are gone
                                        print(f"[!] no response is got. response timeout", flush=True)
                                        return

                                    await asyncio.sleep(0.1)
                                    i += 1
                            if self_verif and len(answers) != 0: 
                                raw_blockchain, reason = e_ver.NodeVerificator.fsync_verifacation(answers)
                                self.node.blockchain = [
                                    e_block.Block.cook(raw) for raw in raw_blockchain
                                ]

                                print(f"[+] new blockchain [{reason}]: {len(self.node.blockchain)} blocks:\n\t{'\n\t'.join([b.hash for b in self.node.blockchain[::-1][:5]])}", flush=True)
                            elif not self_verif and len(answers) != 0:
                                print(f"[+] self_verification disabled", flush=True)
                                return answers
                            else:
                                print(f"[!] no answers are got. please retry your request", flush=True)
                                if len(self.node.blockchain) != 0:
                                    print(f"[!] local version of the blockchain kept ({len(self.node.blockchain)} blocks)", flush=True)
                            return
                        else:
                            print(f"[!] couldn't full sync bc:\n\t{msg}", flush=True)
                            raise RuntimeError(f"Couldn't full sync bc: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def propagate_block(self, block: e_block.Block):
        print(f"[+] starting block propagation", flush=True)
        print(block.stringify(), flush=True)
        print()
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    data = {"token": self.token} | block.rawme()

                    async with session.get(f"{self.const_node}/prp_block", json=data) as req:
                        status, msg = await self.check_answer(req)
                        if status:
                            # self.propagated_block_hashes.append(block.hash)
                            print(f"[>] successfully propagated new block", flush=True)
                            return
                        else:
                            print(f"[!] failed to propagate a new block: {msg}", flush=True)
                            raise RuntimeError(f"Failed to propagate a new block: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def propagate_transac(self, transac: e_tran.Transaction):
        print(f"[+] starting transaction propagation", flush=True)
        data = {"token": self.token} | transac.rawme()
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/prp_transaction", json = data) as req:
                        status, msg = await self.check_answer(req)
                        if status:
                            print(f"[>] successfully propagated new transaction", flush=True)
                            return
                        else:
                            print(f"[!] failed to propagate a new transaction: {msg}", flush=True)
                            raise RuntimeError(f"Failed to propagate a new transaction: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def get_token(self):
        print(f"[+] getting token", flush=True)
        
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/regtoken") as req:
                        status, msg = await self.check_answer(req)
                        
                        if status:
                            data = await req.json()
                            print(f"[>] new token is got: <{data['token']}>", flush=True)
                            self.token = data["token"]
                            return
                        else:
                            print(f"[!] couldn't get a token: {msg}", flush=True)
                            raise RuntimeError(f"Couldn't get a token: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def num_of_nodes(self, nolog=False) -> int:
        if not nolog: print(f"[+] acquiring number of nodes", flush=True)

        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/nodesnum", json={"token": self.token}) as req:
                        status, msg = await self.check_answer(req)
                        
                        if status:
                            data = await req.json()
                            if not nolog: print(f"[>] nodesnum is got: <{data['num']}>", flush=True)
                            return data['num']
                        else:
                            print(f"[!] couldn't get a num of nodes: {msg}", flush=True)
                            raise RuntimeError(f"Couldn't get a num of nodes: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise