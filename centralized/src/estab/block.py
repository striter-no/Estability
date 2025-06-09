from collections import Counter
from typing import Callable
import src.estab.transaction as tr
import time, hashlib, random, decimal

def most_frequent(list_):
    counter = Counter(list_)
    return counter.most_common(1)[0][0]

START_EMISSION = 40
BITS_BLOCKS_CHANGE = 2500
HALVING_BLOCKS = 210_000
TARGET_SECONDS = 120
TRANSACTIONS_IN_BLOCK = 5

def elapsed_time(start) -> tuple[tuple[int, int, int, float], float]:
    elapsed = time.time() - start
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    milliseconds = (elapsed - int(elapsed)) * 1000 

    return (hours, minutes, seconds, milliseconds), elapsed

class Block:
    def __init__(self, transactions: list[tr.Transaction]):
        self.timestamp = time.time()
        self.nonce = 0
        self.phash = "" # Previous hash
        self.bits = ""
        self.merkle = ""
        self.hash = ""
        
        self.transactions: list[tr.Transaction] = transactions

    def get_local_emission(self, blockchain: list) -> float:
        return START_EMISSION / max(1, 2 * max(1, len(blockchain) // HALVING_BLOCKS) if len(blockchain) >= HALVING_BLOCKS else 1)

    def make_emission(self, blockchain: list, address: str, pri_key, pub_key):
        # Halving
        local_emm = self.get_local_emission(blockchain)
        
        t = tr.Transaction(
            tr.TRANSACTION_TYPE.emission,
            "ECC", address,
            time.time(),
            amount = local_emm,
            pub_key = pub_key
        )
        t.hash = t.hashme()
        t.signature = t.signme(pri_key)
        
        self.transactions = [t] + self.transactions

    def merkle_root(self):
        def hash_pair(a, b): return hashlib.sha256((a + b).encode()).hexdigest()

        hashes = [tx.hash for tx in self.transactions]
        if not hashes: return ""

        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            new_hashes = []
            for i in range(0, len(hashes), 2):
                new_hashes.append(hash_pair(hashes[i], hashes[i+1]))
            hashes = new_hashes

        return hashes[0]

    def stringify(self):
        return f"block: {self.hash}\nphash: {self.phash}\ntime: {self.timestamp}\nnonce: {self.nonce}\nmerkle: {self.merkle}\nbits: {self.bits}\ntransactions:\n\t{'\n\t'.join([
            tr.stringify() for tr in self.transactions
        ])}"

    @staticmethod
    def gen_genesis():
        genesis = Block([])
        
        genesis.phash = "0"
        genesis.bits  = "00ff00000000000000000000000000000000000000000000000000000000000"
        genesis.merkle = "0"
        genesis.nonce = 0
        genesis.hash = "0"
        genesis.timestamp = 1748884072

        print(f"[!] genesis block is generated")
        return genesis

    def mine(self, stop_func: Callable = lambda : False) -> tuple[int, float]: # Code of ending, delta
        print(f"[&] starting mining", flush=True)
        bar = "-\\|/-\\|/"
        target, blob = int(self.bits, 16), self.getblob()
        print(f"[+] blob: {blob[:20]}...", flush=True)
        print(f"[+] bits: {self.bits[:20]}...", flush=True)

        hash_rate = 0
        stop_code = 0

        lhashst, start = time.time(), time.time()
        i, t, hshs, nonce = 0, 0, 0, -1
        while not stop_func():
            nonce = random.randint(0, 4294967295)
            hsh = hashlib.sha256(f"{blob}{nonce}".encode()).hexdigest()
            hshs += 1

            if time.time() - lhashst >= 10:
                hash_rate = hshs / (time.time() - lhashst)
                lhashst = time.time()
                hshs = 0

            if t % 100000 == 0:
                (h, m, s, ms), e = elapsed_time(start)
                print(f"\r[{bar[i % len(bar)]}][{h}h:{m}m][{hash_rate * 0.1} H/s] mining block ({self.bits[:20]}...): {nonce}/{h}/{hsh[:20]}...", end = "", flush=True)
                i += 1
            t += 1
            if int(hsh, 16) < target:
                stop_code = 1
                break
        
        self.nonce = nonce
        print(flush=True)
        return stop_code, time.time() - start

    def getblob(self) -> str:
        return f"{self.timestamp}{self.bits}{self.phash}{self.merkle}"

    def hashme(self) -> str:
        return hashlib.sha256(f"{self.getblob()}{self.nonce}".encode()).hexdigest()

    def rawme(self) -> dict:
        if (self.phash == self.hash) and (self.hash != "0"):
            raise RuntimeError(f"[rawme] Block {self.hash} is self-parented:\n{self.stringify()}\n")

        return {
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "phash": self.phash,
            "bits": self.bits,
            "hash": self.hash,
            "merkle": self.merkle,
            "transactions": [t.rawme() for t in self.transactions]
        }
    
    def calcbits(self, blockchain: list) -> str:
        if len(blockchain) % BITS_BLOCKS_CHANGE == 0 and len(blockchain) != 0:
            minedelta = (time.time() - blockchain[len(blockchain) - BITS_BLOCKS_CHANGE]) / BITS_BLOCKS_CHANGE
            return hex(round(decimal.Decimal(int(self.bits, 16)) * max(decimal.Decimal(0.25), min(4, decimal.Decimal(TARGET_SECONDS / minedelta)))))[2:]
        return self.bits
    
    async def checkme(self, node, prev_block = None, text_check: Callable | None = None, phash_agrs_check = False, pre_prev_block = None) -> tuple[bool, str]:
        """
        Returns: (is_valid, error_message)
        """

        print(f"[?] checking {self.hash[:5]}")

        # 0. Проверить сложность на адекватность
        this_period_blocks = node.blockchain[(BITS_BLOCKS_CHANGE * (len(node.blockchain) // BITS_BLOCKS_CHANGE)):]
        most_freq = most_frequent([b.bits for b in this_period_blocks])

        if (self.phash == self.hash) and (self.hash != "0"):
            raise RuntimeError(f"[checkme] Block {self.hash} is self-parented:\n{self.stringify()}\n")

        if self.bits < most_freq:
            return False, f"Invalid block bits (less than most_freq:{most_freq} > {self.bits})"

        # 1. Проверка корректности собственного хеша
        if self.hash != self.hashme():
            return False, f"Invalid block hash ({self.hash} != {self.hashme()})\n: {self.stringify()}\nHASH: {self.hashme()}\n\n"

        # 2. Проверка соответствия хешу сложности
        target = int(self.bits, 16)
        if int(self.hash, 16) >= target:
            return False, f"Hash doesn't meet difficulty target ({self.hash} >= {self.bits})"

        # 3. Эффективная проверка предыдущего блока
        non_agressive_ok = False
        if prev_block:
            if self.phash != prev_block.hash and len(node.blockchain) != 0 and not phash_agrs_check:
                return False, f"Previous hash mismatch ({self.phash} != {prev_block.hash})"
            elif self.phash != prev_block.hash and phash_agrs_check and len(node.blockchain) != 0 and pre_prev_block:
                # Non-agressive previous check
                if self.phash != pre_prev_block.hash:
                    return False, f"Non-agressive phash failed ({self.phash} != {pre_prev_block.hash})"
                else:
                    non_agressive_ok = True
        else:
            # Fallback к поиску в блокчейне (только если prev_block не передан)
            if not self._validate_previous_hash(node.blockchain):
                return False, "Previous block not found"

        # 4. Проверка временной метки
        s = self._validate_timestamp(prev_block)
        if s != 4:
            return False, f"Invalid timestamp: code ({s})"

        # 5. Проверка формата bits
        if not self._validate_bits_format():
            return False, "Invalid bits format"
        
        if self.merkle_root() != self.merkle and len(node.blockchain) != 0:
            return False, "Wrong Merkle root"

        emission_n = 0
        for t in self.transactions:
            s, msg = await t.checkme(node, len(node.blockchain), text_check)
            if not s:
                return False, f"Invalid transaction: {msg}"
            if t.ttype == tr.TRANSACTION_TYPE.emission:
                emission_n += 1
        
        if emission_n != 1:
            return False, f"Invalid emission transactions number ({emission_n})"

        if len(self.transactions) <= 1:
            return False, "Empty transactions block"

        print(f"[?!] block {self.hash} seems to be really nice!")

        for t in self.transactions:
            if t.ttype == tr.TRANSACTION_TYPE.emission and t.amount > self.get_local_emission(node.blockchain): 
                return False, f"Invalid transaction: emission overspending ({t.input}/{t.amount})"

        print(f"[>>] block {self.hash} is a valid block")

        return True, "non_agressive_ok" if non_agressive_ok else "Valid block"

    def _validate_previous_hash(self, blockchain: list) -> bool:
        """Эффективная проверка предыдущего хеша"""
        if not blockchain:
            return self.phash == "0"  # Genesis block

        # Проверяем только последний блок (для последовательной валидации)
        return blockchain[-1].hash == self.phash

    def _validate_timestamp(self, prev_block = None) -> int:
        """Проверка временной метки"""
        current_time = time.time()

        # Блок не может быть из будущего (с небольшим допуском)
        if self.timestamp > current_time + 7200:  # 2 часа допуск
            return 1

        # Блок должен быть после предыдущего
        if prev_block and self.timestamp < prev_block.timestamp:
            return 2
        
        if prev_block and self.timestamp == prev_block.timestamp:
            return 3

        return 4

    def _validate_bits_format(self) -> bool:
        """Проверка формата bits"""
        try:
            int(self.bits, 16)
            return True
            # return len(self.bits) <= 8  # Разумное ограничение
        except ValueError:
            return False

    @staticmethod
    def cook(rawdata: dict):
        block = Block([])
        
        block.timestamp = rawdata["timestamp"]
        block.nonce = rawdata["nonce"]
        block.phash = rawdata["phash"]
        block.bits = rawdata["bits"]
        block.hash = rawdata["hash"]
        block.merkle = rawdata["merkle"]
        block.transactions = [tr.Transaction.cook(rt) for rt in rawdata["transactions"]]
        
        if (block.phash == block.hash) and block.hash != '0':
            raise RuntimeError(f"[cook] Block {block.hash} is self-parented:\n{block.stringify()}\n")

        return block