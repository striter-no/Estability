from typing import Callable

import asyncio
import aiohttp
import time, uuid

import src.estab.block as e_block
import src.estab.transaction as e_tran
import src.estab.verificator as e_ver
import src.estab.user as e_user

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
        print(f"[!] blockchain len: {len(self.blockchain)}")
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
        print(f"[+] sending answer to <{req_uuid}>: {str(answer_body).replace('\\n', ' ')[:50]}")
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
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise
        return False, "Network failure"

    async def check_pending_req(self, nolog = False) -> Request | None:
        if not nolog: print(f"[+] checking pending requests")
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
                            if not nolog: print(f"[>] request getted:\n\t{data['type']}-{data['entity']}-{data['uuid']}-{data['timestamp']}-{str(data['body']).replace('\\n', ' ')[:50]}")
                            return Request(data["type"], data["entity"], data["body"], data["uuid"], data["timestamp"])
                        elif not msg.startswith("warning"):
                            print(f"[!] couldnt get pending requests")
                            raise RuntimeError(f"Couldn't get pending request: {msg}")
                        else:
                            if not nolog: print(f"[$] no pending requests are available")
                            return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def new_block_sync(self, nolog = False) -> e_block.Block | None:
        if not nolog: print(f"[+] new block syncing...")
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
                            #     if not nolog: print(f"[<>] skiping self-propagated block")
                            #     return
                            i = 0
                            if not nolog: print(f"[*] update request successeded, getting answer")

                            while True:
                                async with session.get(f"{self.const_node}/check", json={
                                    "token": self.token,
                                    "uuid": rec_uuid
                                }) as req_check:
                                    status, msg = await self.check_answer(req_check)

                                    if status:
                                        if not nolog: print(f"[>] new blocks are getted")
                                        data = await req_check.json()
                                        answers = [e_block.Block.cook(b) for b in data["answers"]]
                                        # Check for duplicates
                                        for b in answers:
                                            if b.hash in self.new_block_hashes:
                                                continue
                                            
                                            self.new_block_hashes.append(b.hash)
                                            
                                            s, msg = await b.checkme(self.node, self.node.blockchain[-1], self.text_transac_check)
                                            if not s:
                                                if not (b.hash in [oldb.hash for oldb in self.node.blockchain]):
                                                    print(f"[!] block <{b.hash}> is uncomfired: {msg}")
                                                continue # Skip malicious ones
                                            if b.hash in [oldb.hash for oldb in self.node.blockchain]:
                                                continue

                                            # Aim especially for new ones (5s diffrence)
                                            if abs(time.time() - b.timestamp) <= 5:
                                                self.node.blockchain.append(b)
                                                if not nolog: print(f"[!] getted new block: <{b.hash}>")
                                                return b
                                        # Done
                                        if not nolog: print(f"[!] no new blocks are correct" if len(answers) != 0 else "[!] no new blocks was obtained (no answers)" )
                                        return None
                                    elif i >= 20: # 2 seconds are gone
                                        if not nolog: print(f"[!] response time out")
                                        return
                                    elif not status and not msg.startswith("warning"):
                                        if not nolog: print(f"[!] couldn't get new blocks: {msg}")
                                        return

                                    await asyncio.sleep(0.1)
                                    i += 1
                        else:
                            if not nolog: print(f"[!] couldn't get new blocks:\n\t{msg}")
                            raise RuntimeError(f"Couldn't get new blocks: {msg}")
                break
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def new_transac_sync(self, nolog = False):
        if not nolog: print(f"[+] new transactions sync was called")
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
                            if not nolog: print(f"[+] getted uuid for newtransac request: <{rec_uuid}>")

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

                                            if not (await t.checkme(len(self.node.blockchain), self.text_transac_check)):
                                                continue # Skip malicious ones

                                            self.node.transactions.append(t)
                                        return
                                        # Done
                                    elif i >= 20: # 2 seconds are gone
                                        if not nolog: print(f"[!] response time out")
                                        return
                                    elif not status and not msg.startswith("warning"):
                                        if not nolog: print(f"[!] couldn't get transaction: {msg}")
                                        return

                                    await asyncio.sleep(0.1)
                                    i += 1
                        else:
                            if not nolog: print(f"[!] couldn't get new transactions:\n\t{msg}")
                            raise RuntimeError(f"Couldn't get new transactions: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def full_bc_sync(self):
        print(f"[+] starting full BC sync")
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
                            print(f"[*] request successeded: <{req_uuid}>")
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
                                        print(f"[>] answers getted: {str(answers).replace('\\n', ' ')[:50]}")
                                        break
                                    elif not msg.startswith("warning"):
                                        print(f"[!] couldn't full sync bc and check answers:\n\t{msg}")
                                        raise RuntimeError(f"Couldn't full sync bc and check answers: {msg}")
                                    elif i > 20: # 2 seconds are gone
                                        print(f"[!] no response is getted. response timeout")
                                        return

                                    await asyncio.sleep(0.1)
                                    i += 1
                            if len(answers) != 0: 
                                raw_blockchain, reason = e_ver.NodeVerificator.fsync_verifacation(answers)
                                self.node.blockchain = [
                                    e_block.Block.cook(raw) for raw in raw_blockchain
                                ]

                                print(f"[+] new blockchain [{reason}]: {len(self.node.blockchain)} blocks:\n\t{'\n\t'.join([b.hash for b in self.node.blockchain[::-1][:5]])}")
                            else:
                                print(f"[!] no answers are getted. please retry your request")
                                if len(self.node.blockchain) != 0:
                                    print(f"[!] local version of the blockchain kept ({len(self.node.blockchain)} blocks)")
                            return
                        else:
                            print(f"[!] couldn't full sync bc:\n\t{msg}")
                            raise RuntimeError(f"Couldn't full sync bc: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def propagate_block(self, block: e_block.Block):
        print(f"[+] starting block propagation")
        print(block.stringify())
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
                            print(f"[>] successfully propagated new block")
                            return
                        else:
                            print(f"[!] failed to propagate a new block: {msg}")
                            raise RuntimeError(f"Failed to propagate a new block: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def propagate_transac(self, transac: e_tran.Transaction):
        print(f"[+] starting transaction propagation")
        data = {"token": self.token} | transac.rawme()
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/prp_transaction", json = data) as req:
                        status, msg = await self.check_answer(req)
                        if status:
                            print(f"[>] successfully propagated new transaction")
                            return
                        else:
                            print(f"[!] failed to propagate a new transaction: {msg}")
                            raise RuntimeError(f"Failed to propagate a new transaction: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    async def get_token(self):
        print(f"[+] getting token")
        
        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.const_node}/regtoken") as req:
                        status, msg = await self.check_answer(req)
                        
                        if status:
                            data = await req.json()
                            print(f"[>] new token is getted: <{data['token']}>")
                            self.token = data["token"]
                            return
                        else:
                            print(f"[!] couldn't get a token: {msg}")
                            raise RuntimeError(f"Couldn't get a token: {msg}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                print(f"[!] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    raise