# How to start mining

1. After "curling" and unzipping your archive:
    
    1. Create `python virtual environment`:

    ```shell
    python -m venv venv
    ```

    2. Install all dependencies:

    ```shell
    pip install -r ./requirements.txt
    ```
    
    3. Create runtime directories and config files:

    ```shell
    python ./create_runtime.py
    ```

    4. Edit `configs/tg_app_conf.json` with your data

    5. Change IP and *.pem in files: `client.py` and `transac_creator.py`

    6. Start your miner:

    ```shell
    python ./client.py
    ```