import os, json

os.makedirs("./runtime/blockchains", exist_ok=True)
os.makedirs("./runtime/databases", exist_ok=True)
os.makedirs("./runtime/pems", exist_ok=True)
os.makedirs("./runtime/sessions", exist_ok=True)
os.makedirs("./configs", exist_ok=True)

with open("./configs/tg_app_conf.json", "w") as f:
    json.dump({"API_HASH": "", "API_ID": 123}, f)