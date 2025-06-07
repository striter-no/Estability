# Estability [chain][coin]
# Node [flask] v 0.0.1
# Estability v 0.0.3
# Protocol v 1
#
# Features:
# - send broadcast
# - send survies [broadcast with time releated answers][15s]
#
# TODO:
# - link with other nodes
#   |
#   |_ sync broadcasts
#   |_ sync survies


from flask import Flask, jsonify, request
import src.database as db
import asyncio
import uuid
import time

import os
import io
import zipfile
from flask import send_file

import src.estab.block as e_block
import src.estab.transaction as e_tran

users = db.DataBase("./runtime/databases/users.sqlite3")
app = Flask(__name__)

class Request:
    def __init__(self, type: str, entity: str, body: str, author: str, immediate_ans = False):
        self.type = type
        self.entity = entity
        self.body = body
        self.answers = []
        self.author = author
        self.immediate_ans = immediate_ans

        self.uuid = str(uuid.uuid4())
        self.timestamp = time.time()

requests: dict[str, Request] = {}
new_blocks: list[tuple[e_block.Block, str]] = []
new_transactions: list[tuple[e_tran.Transaction, str]] = []

# /regtoken route
# need: creates a new token for users and writes it to the database
#
# returns: on success returns a new token
@app.route('/regtoken', methods=['GET'])
async def regtoken():
    token = str(uuid.uuid4())

    users.ensure_set("tokens", [])
    users.set(
        "tokens", users.get("tokens") + [token]
    )

    return jsonify({
        "status": "ok",
        "token": token
    })

# /prp_block route
# need: propagates new block to other network users
#
# returns: status of the response
@app.route('/prp_block')
async def prp_block():
    global requests
    global new_blocks

    try: data = request.json
    except: data = None

    if data is None:
        return jsonify({
            "status": "fatal-error",
            "reason": "no json data is provided. requested: token"
        })

    token = data.get("token")
    if token is None: return jsonify({ "status": "fatal-error", "reason": "no token is provided in json data" })

    normal = []
    for b, author in new_blocks:
        if time.time() - b.timestamp < 60 * 5: # Less than 5 minutes was gone 
            normal.append((b, author))
    
    new_blocks = normal.copy()
    new_blocks.append((e_block.Block.cook(data), token))

    return jsonify({ "status": "ok", "message": "block started to propagate" })

# /prp_transaction route
# need: propagates new transaction to other network users
#
# returns: status of the response
@app.route('/prp_transaction')
async def prp_transaction():
    global requests
    global new_transactions

    try: data = request.json
    except: data = None

    if data is None:
        return jsonify({
            "status": "fatal-error",
            "reason": "no json data is provided. requested: token"
        })

    token = data.get("token")
    if token is None: return jsonify({ "status": "fatal-error", "reason": "no token is provided in json data" })

    normal = []
    for t, author in new_transactions:
        if time.time() - t.timestamp < 60 * 5: # Less than 5 minutes was gone 
            normal.append((t, author))

    new_transactions = normal.copy()
    new_transactions.append((e_tran.Transaction.cook(data), token))

    return jsonify({ "status": "ok", "message": "transaction started to propagate" })

# /jupdate route
# need: helping to acquire new pending requests (for sync for example)
#
# returns: on success returns uuid, timestamp, type, entity and body of pending request
@app.route("/jupdate")
async def jupdate():
    global requests
    try: data = request.json
    except: data = None

    if data is None:
        return jsonify({
            "status": "fatal-error",
            "reason": "no json data is provided. requested: token"
        })

    token = data.get("token")
    if token is None:    return jsonify({ "status": "fatal-error", "reason": "no token is provided in json data" })

    if len(requests) != 0:
        ruuid = None
        r = None
        for i in range(len(requests)):
            ruuid = list(requests)[i]
            if requests[ruuid].author != token and not requests[ruuid].immediate_ans:
                r = requests[ruuid]

        if ruuid is None or r is None:
            return jsonify({
                "status": "warning",
                "reason": "no requests are available"
            }) 

        return jsonify({
            "status": "ok",
            "uuid": r.uuid,
            "timestamp": r.timestamp,
            "type": r.type,
            "entity": r.entity,
            "body": r.body
        })

    return jsonify({"status": "warning", "reason": "no requests are available"})

# /answer route
# need: answers on requests with provided answer's body
#
# returns: on success returns only success status
@app.route('/answer')
async def answer():
    global requests
    try: data = request.json
    except: data = None

    if data is None:
        return jsonify({
            "status": "fatal-error",
            "reason": "no json data is provided. requested: token/uuid/body"
        })

    token = data.get("token")
    uuid_ans = data.get("uuid")
    answer_body = data.get("body")
    
    if token is None:       return jsonify({ "status": "fatal-error", "reason": "no token is provided in json data" })
    if uuid_ans is None:    return jsonify({ "status": "fatal-error", "reason": "no uuid of request to answer is provided in json data" })
    if answer_body is None: return jsonify({ "status": "fatal-error", "reason": "no answer's body is provided in json data" })

    requests[uuid_ans].answers.append(answer_body)

    return jsonify({"status": "ok"})

# /update route
# need: requests an update for node
#       or blockchain or new block or new transaction
#       for this a new internal request is generated
#
# returns: on success returns uuid and timestamp of the request
#          client memorizes the uuid and later checks answers
@app.route('/update')
async def update_target():
    global requests
    try: data = request.json
    except: data = None

    if data is None:
        return jsonify({
            "status": "fatal-error",
            "reason": "no json data is provided. requested: token/target"
        })

    token = data.get("token")
    upd_target = data.get("target")

    if token is None:      return jsonify({ "status": "fatal-error", "reason": "no token is provided in json data" })
    if upd_target is None: return jsonify({ "status": "fatal-error", "reason": "no update target is provided in json data" })
    
    nr = Request("", "", "", token)
    match upd_target:
        case "blockchain":
            nr = Request("sync", "bc", "", token)
            requests[nr.uuid] = nr

        case "newblock":
            nr = Request("sync", "newblock", "", token, True)
            requests[nr.uuid] = nr

        case "newtransac":
            nr = Request("sync", "newtransac", "", token, True)
            requests[nr.uuid] = nr

        case _:
            return jsonify({
                "status": "error",
                "reason": f"no such target to update \"{upd_target}\""
            })

    return jsonify({
        "status": "ok", 
        "uuid": nr.uuid,
        "timestamp": nr.timestamp,
        "message": "request is send"
    })

# /check route
# need: checks the answers to provided request
# 
# returns: after 15 seconds from the request creation can return
#          answers to this request from other users
@app.route("/check")
def check_request():
    global requests
    try: data = request.json
    except: data = None

    if data is None:
        return jsonify({
            "status": "fatal-error",
            "reason": "no json data is provided. requested: token/uuid"
        })

    token = data.get("token")
    req_uuid = data.get("uuid")
    if token is None:    return jsonify({ "status": "fatal-error", "reason": "no token is provided in json data" })
    if req_uuid is None: return jsonify({ "status": "fatal-error", "reason": "no request's uuid is provided in json data" })

    if not requests[req_uuid].immediate_ans and (time.time() - requests[req_uuid].timestamp < 3):
        return jsonify({
            "status": "warning",
            "reason": "request's time to answer is not done yet"
        })
    
    rr = requests[req_uuid]
    if rr.immediate_ans:
        if rr.type == "sync" and rr.entity == "newblock":
            rr.answers = [b.rawme() for (b, a) in new_blocks]
        elif rr.type == "sync" and rr.entity == "newtransac":
            rr.answers = [t.rawme() for (t, a) in new_transactions]

    ans = requests[req_uuid].answers
    del requests[req_uuid]

    return jsonify({
        "status": "ok",
        "answers": ans
    })

@app.route('/clone_miner.zip')
def clone_miner():
    print(f"Cloning!")
    # Files and directories to include
    include_paths = [
        'client.py',
        'CATME.md',
        'create_runtime.py',
        'transac_creator.py',
        'src',
        'requirements.txt'
    ]

    # Create in-memory zip archive
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in include_paths:
            if os.path.isfile(path):
                # Add file directly
                zf.write(path)
            elif os.path.isdir(path):
                # Walk directory
                for root, dirs, files in os.walk(path):
                    # Exclude __pycache__ directories
                    dirs[:] = [d for d in dirs if d != '__pycache__']
                    for file in files:
                        if file == '__pycache__':
                            continue
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, '.')  # relative path in zip
                        zf.write(file_path, arcname)

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='clone_miner.zip'
    )

if __name__ == '__main__':
    app.run(host="192.168.31.100", port=9001)