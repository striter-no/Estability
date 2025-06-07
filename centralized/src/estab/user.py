from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
import hashlib
import base64
import os

def generate_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    return private_key, public_key

def public_key_to_address(public_key):
    # Получаем публичный ключ в PEM-формате
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    # Хэшируем публичный ключ (SHA-256)
    digest = hashlib.sha256(pem).digest()
    # Кодируем в base64 (можно использовать .hex() для hex-строки)
    address = base64.urlsafe_b64encode(digest).decode('utf-8')
    return address

class User:
    def __init__(
            self,
            pri_key_path: str
    ):
        if os.path.exists(pri_key_path):
            with open(pri_key_path, "rb") as key_file:
                PRIVATE_KEY = serialization.load_pem_private_key(
                    key_file.read(),
                    password = None,
                )
        else:
            PRIVATE_KEY, pb = generate_key_pair()
            with open(pri_key_path, "wb") as f:
                pem = PRIVATE_KEY.private_bytes(
                    encoding = serialization.Encoding.PEM,
                    format = serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm = serialization.NoEncryption()
                )
                f.write(pem)

        self.private_key = PRIVATE_KEY
        self.public_key = PRIVATE_KEY.public_key()
        self.address = public_key_to_address(self.public_key)

if __name__ == "__main__":
    user = User("./quitearno.pem")
    print(user.address)