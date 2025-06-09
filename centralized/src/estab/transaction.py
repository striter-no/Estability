from typing import Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import hashlib
import base64
import enum
import time

START_EMISSION = 100
BITS_BLOCKS_CHANGE = 20_000
HALVING_BLOCKS = 540_000
TARGET_SECONDS = 120

def private_serialize(pri_key):
    return pri_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

def private_deserialize(pri_key_data: str):
    return serialization.load_pem_private_key(
        pri_key_data.encode('utf-8'),
        password=None,
        backend=default_backend()
    )

def public_serialize(pub_key):
    return pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

def public_deserialize(pub_key_data: str):
    return serialization.load_pem_public_key(
        pub_key_data.encode('utf-8'),
        backend=default_backend()
    )

class TRANSACTION_TYPE(enum.Enum):
    coin = 0
    text = 1
    emission = 2

class Transaction:
    def __init__(
            self,
            ttype: TRANSACTION_TYPE,
            input: str,
            output: str,
            timestamp: float,
            text: str = "",
            amount: float = 0,
            pub_key = None
    ) -> None:
        self.ttype = ttype
        self.input = input
        self.output = output
        self.text = text
        self.amount = amount
        self.timestamp = timestamp

        self.pub_key = pub_key
        self.hash = ""
        self.signature = ""

    def stringify(self):
        return f"prefix:{self.ttype.value}|{self.input}->{self.output}|{self.amount}|{self.text.replace('\n', '  ')[:50]}|{self.hash[:20]}"

    def verify_sign(self, public_key):
        """Проверяет подпись транзакции"""
        if not self.signature:
            return False

        try:
            signature_bytes = base64.b64decode(self.signature)
            public_key.verify(
                signature_bytes,
                self.hash.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except:
            return False

    def signme(self, private_key):
        if not private_key:
            return ""

        signature = private_key.sign(
            self.hash.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode()

    def hashme(self) -> str:
        typesd = {member.name: member.value for member in TRANSACTION_TYPE}
        return hashlib.sha256(f"{typesd[self.ttype.name]}{self.timestamp}{self.input}{self.output}{self.text}{self.amount}".encode()).hexdigest()

    async def checkme(self, node, block_depth = 0, text_check: Callable | None = None) -> tuple[bool, str]:
        print(f"[!] checking transaction")
        """Validates the transaction integrity"""
        # Recalculate hash and compare
        calculated_hash = self.hashme()
        if self.hash != calculated_hash:
            print(f"[>>] hash dismatch")
            return False, "Hash dismatch"

        # For signed transactions, verify signature
        if self.ttype in [TRANSACTION_TYPE.coin, TRANSACTION_TYPE.emission]:
            if not self.pub_key or not self.signature:
                print(f"[>>] no data for signature ({', '.join(["pub_key missing" if not self.pub_key else "", "signature missing" if not self.signature else ""])})")
                return False, "No data for signature"
            if self.amount < 1:
                print(f"[>>] negative emission: {self.amount} < 1")
                return False, "Negative emission"
            if self.ttype == TRANSACTION_TYPE.coin and node.check_balance(self.input) < self.amount: 
                return False, f"Invalid transaction: overspending ({self.input}/{self.amount})"

            print(f"[$] signature verification: {self.verify_sign(self.pub_key)}")
            return self.verify_sign(self.pub_key), "Signature verification"

        if self.ttype == TRANSACTION_TYPE.emission:
            local_emm = START_EMISSION / max(1, 2 * max(1, block_depth // HALVING_BLOCKS) if block_depth >= HALVING_BLOCKS else 1)
            if self.amount > local_emm:
                print(f"[>>] too much emission: {self.amount} > {local_emm}")
                return False, "Too much emission"
            if self.amount < 1:
                print(f"[>>] negative emission: {self.amount} < 1")
                return False, "Negative emission"

        if self.ttype == TRANSACTION_TYPE.text:
            if not text_check:
                print(f"[!!!] No transaction check for text type")
                return True, "No transaction check for text type"
            
            s, reason = await text_check(self)
            if not s:
                print(f"[!] text verification failed: {reason}")
                return False, reason

        print(f"[!] transaction is ok")
        return True, "Ok"

    @staticmethod
    def cook(data: dict):
        match data["prefix"]:
            case "0":
                t = Transaction(
                    TRANSACTION_TYPE.text,
                    data["input"], 
                    data["output"],
                    data["timestamp"],
                    text=data["text"]
                )
                t.hash = data["hash"]
                return t
            case "1":
                t = Transaction(
                    TRANSACTION_TYPE.coin, 
                    data["input"], 
                    data["output"],
                    data["timestamp"], 
                    amount=data["amount"], 
                    pub_key=public_deserialize(data["pubkey"])
                )
                t.hash = data["hash"]
                t.signature = data["sign"]
                return t
            
        t = Transaction(
            TRANSACTION_TYPE.emission, 
            "ECC", 
            data["output"],
            data["timestamp"], 
            amount=data["amount"], 
            pub_key=public_deserialize(data["pubkey"])
        )
        t.hash = data["hash"]
        t.signature = data["sign"]
        
        return t

    def rawme(self) -> dict:
        match self.ttype:
            case TRANSACTION_TYPE.text:
                return {
                    "prefix": "0",
                    "input": self.input,
                    "output": self.output,
                    "text": self.text,
                    "hash": self.hash,
                    "timestamp": self.timestamp
                }
            case TRANSACTION_TYPE.coin:
                return {
                    "prefix": "1",
                    "input": self.input,
                    "output": self.output,
                    "amount": self.amount,
                    "hash": self.hash,
                    "pubkey": public_serialize(self.pub_key),
                    "sign": self.signature,
                    "timestamp": self.timestamp
                }
            case TRANSACTION_TYPE.emission:
                return {
                    "prefix": "2",
                    "output": self.output,
                    "amount": self.amount,
                    "hash": self.hash,
                    "pubkey": public_serialize(self.pub_key),
                    "sign": self.signature,
                    "timestamp": self.timestamp
                }