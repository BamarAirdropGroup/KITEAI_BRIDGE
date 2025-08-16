import asyncio
import json
import re
import os
import pytz
import random
from datetime import datetime, timezone
from web3 import Web3
from web3.exceptions import TransactionNotFound
from eth_account import Account
from aiohttp import ClientResponseError, ClientSession, ClientTimeout, BasicAuth
from aiohttp_socks import ProxyConnector
from fake_useragent import FakeUserAgent
from colorama import *

wib = pytz.timezone('Asia/Singapore')

class KiteAi:
    def __init__(self) -> None:
        self.KITE_AI = {
            "name": "KITE AI",
            "rpc_url": "https://rpc-testnet.gokite.ai/",
            "explorer": "https://testnet.kitescan.ai/tx/",
            "tokens": [
                { "type": "native", "ticker": "KITE", "address": "0x0BBB7293c08dE4e62137a557BC40bc12FA1897d6" },
                { "type": "erc20", "ticker": "Bridged ETH", "address": "0x7AEFdb35EEaAD1A15E869a6Ce0409F26BFd31239" }
            ],
            "chain_id": 2368
        }
        self.BASE_SEPOLIA = {
            "name": "BASE SEPOLIA",
            "rpc_url": "https://base-sepolia-rpc.publicnode.com/",
            "explorer": "https://sepolia.basescan.org/tx/",
            "tokens": [
                { "type": "native", "ticker": "ETH", "address": "0x226D7950D4d304e749b0015Ccd3e2c7a4979bB7C" },
                { "type": "erc20", "ticker": "Bridged KITE", "address": "0xFB9a6AF5C014c32414b4a6e208a89904c6dAe266" }
            ],
            "chain_id": 84532
        }
        self.NATIVE_CONTRACT_ABI = json.loads('''[
            {"type":"function","name":"send","stateMutability":"payable","inputs":[{"name":"_destChainId","type":"uint256"},{"name":"_recipient","type":"address"},{"name":"_amount","type":"uint256"}],"outputs":[]}
        ]''')
        self.ERC20_CONTRACT_ABI = json.loads('''[
            {"type":"function","name":"send","stateMutability":"nonpayable","inputs":[{"name":"_destChainId","type":"uint256"},{"name":"_recipient","type":"address"},{"name":"_amount","type":"uint256"}],"outputs":[]},
            {"type":"function","name":"balanceOf","stateMutability":"view","inputs":[{"name":"address","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
            {"type":"function","name":"decimals","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"uint8"}]}
        ]''')
        self.BRIDGE_API = "https://bridge-backend.prod.gokite.ai"
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}
        self.BRIDGE_HEADERS = {}
        self.config_file = "bridge_config.json"
        self.load_config()

    def load_config(self):
        """Load bridge configuration from a JSON file if it exists."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.bridge_count = config.get('bridge_count', 0)
                    self.min_bridge_amount = config.get('min_bridge_amount', 0.0)
                    self.max_bridge_amount = config.get('max_bridge_amount', 0.0)
            else:
                self.bridge_count = 0
                self.min_bridge_amount = 0.0
                self.max_bridge_amount = 0.0
        except Exception as e:
            self.log(f"{Fore.RED + Style.BRIGHT}Failed to load config: {e}{Style.RESET_ALL}")
            self.bridge_count = 0
            self.min_bridge_amount = 0.0
            self.max_bridge_amount = 0.0

    def save_config(self):
        """Save bridge configuration to a JSON file."""
        try:
            config = {
                'bridge_count': self.bridge_count,
                'min_bridge_amount': self.min_bridge_amount,
                'max_bridge_amount': self.max_bridge_amount
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.log(f"{Fore.RED + Style.BRIGHT}Failed to save config: {e}{Style.RESET_ALL}")

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def log(self, message):
        print(
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}{message}",
            flush=True
        )

    def welcome(self):
        print(
            f"""
        {Fore.GREEN + Style.BRIGHT}   Kite Ai - {Fore.BLUE + Style.BRIGHT}Bridge BOT
            """
            f"""
        {Fore.GREEN + Style.BRIGHT} {Fore.YELLOW + Style.BRIGHT}
            """
        )

    def format_seconds(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    async def load_proxies(self, use_proxy_choice: int):
        filename = "proxy.txt"
        try:
            if use_proxy_choice == 1:
                async with ClientSession(timeout=ClientTimeout(total=30)) as session:
                    async with session.get("https://raw.githubusercontent.com/monosans/proxy-list/refs/heads/main/proxies/all.txt") as response:
                        response.raise_for_status()
                        content = await response.text()
                        with open(filename, 'w') as f:
                            f.write(content)
                        self.proxies = [line.strip() for line in content.splitlines() if line.strip()]
            else:
                if not os.path.exists(filename):
                    self.log(f"{Fore.RED + Style.BRIGHT}File {filename} Not Found.{Style.RESET_ALL}")
                    return
                with open(filename, 'r') as f:
                    self.proxies = [line.strip() for line in f.read().splitlines() if line.strip()]

            if not self.proxies:
                self.log(f"{Fore.RED + Style.BRIGHT}No Proxies Found.{Style.RESET_ALL}")
                return

            self.log(
                f"{Fore.GREEN + Style.BRIGHT}Proxies Total  : {Style.RESET_ALL}"
                f"{Fore.WHITE + Style.BRIGHT}{len(self.proxies)}{Style.RESET_ALL}"
            )

        except Exception as e:
            self.log(f"{Fore.RED + Style.BRIGHT}Failed To Load Proxies: {e}{Style.RESET_ALL}")
            self.proxies = []

    def check_proxy_schemes(self, proxies):
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        if any(proxies.startswith(scheme) for scheme in schemes):
            return proxies
        return f"http://{proxies}"

    def get_next_proxy_for_account(self, account):
        if account not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[account] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[account]

    def rotate_proxy_for_account(self, account):
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[account] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy

    def build_proxy_config(self, proxy=None):
        if not proxy:
            return None, None, None

        if proxy.startswith("socks"):
            connector = ProxyConnector.from_url(proxy)
            return connector, None, None

        elif proxy.startswith("http"):
            match = re.match(r"http://(.*?):(.*?)@(.*)", proxy)
            if match:
                username, password, host_port = match.groups()
                clean_url = f"http://{host_port}"
                auth = BasicAuth(username, password)
                return None, clean_url, auth
            else:
                return None, proxy, None

        raise Exception("Unsupported Proxy Type.")

    def generate_address(self, account: str):
        try:
            account = Account.from_key(account)
            address = account.address
            return address
        except Exception as e:
            return None

    def mask_account(self, account):
        try:
            mask_account = account[:6] + '*' * 6 + account[-6:]
            return mask_account
        except Exception as e:
            return None

    def generate_bridge_payload(self, address: str, src_chain_id: int, dest_chain_id: int, src_token: str, dest_token: str, amount: int, tx_hash: str):
        try:
            now_utc = datetime.now(timezone.utc)
            timestamp = now_utc.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

            payload = {
                "source_chain_id": src_chain_id,
                "target_chain_id": dest_chain_id,
                "source_token_address": src_token,
                "target_token_address": dest_token,
                "amount": str(amount),
                "source_address": address,
                "target_address": address,
                "tx_hash": tx_hash,
                "initiated_at": timestamp
            }
            return payload
        except Exception as e:
            raise Exception(f"Generate Bridge Payload Failed: {str(e)}")

    def get_bridge_sequence(self):
        return [
            {
                "option": "BASE SEPOLIA to KITE AI (ETH)",
                "rpc_url": self.BASE_SEPOLIA["rpc_url"],
                "explorer": self.BASE_SEPOLIA["explorer"],
                "src_chain_id": self.BASE_SEPOLIA["chain_id"],
                "dest_chain_id": self.KITE_AI["chain_id"],
                "src_token": self.BASE_SEPOLIA["tokens"][0],
                "dest_token": self.KITE_AI["tokens"][1]    
            },
            {
                "option": "KITE AI to BASE SEPOLIA (ETH)",
                "rpc_url": self.KITE_AI["rpc_url"],
                "explorer": self.KITE_AI["explorer"],
                "src_chain_id": self.KITE_AI["chain_id"],
                "dest_chain_id": self.BASE_SEPOLIA["chain_id"],
                "src_token": self.KITE_AI["tokens"][1],    
                "dest_token": self.BASE_SEPOLIA["tokens"][0]
            },
            {
                "option": "KITE AI to BASE SEPOLIA (KITE)",
                "rpc_url": self.KITE_AI["rpc_url"],
                "explorer": self.KITE_AI["explorer"],
                "src_chain_id": self.KITE_AI["chain_id"],
                "dest_chain_id": self.BASE_SEPOLIA["chain_id"],
                "src_token": self.KITE_AI["tokens"][0],
                "dest_token": self.BASE_SEPOLIA["tokens"][1]
            },
            {
                "option": "BASE SEPOLIA to KITE AI (KITE)",
                "rpc_url": self.BASE_SEPOLIA["rpc_url"],
                "explorer": self.BASE_SEPOLIA["explorer"],
                "src_chain_id": self.BASE_SEPOLIA["chain_id"],
                "dest_chain_id": self.KITE_AI["chain_id"],
                "src_token": self.BASE_SEPOLIA["tokens"][1],
                "dest_token": self.KITE_AI["tokens"][0]    
            }
        ]

    async def get_web3_with_check(self, address: str, rpc_url: str, use_proxy: bool, retries=3, timeout=60):
        request_kwargs = {"timeout": timeout}
        proxy = self.get_next_proxy_for_account(address) if use_proxy else None

        if use_proxy and proxy:
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}

        for attempt in range(retries):
            try:
                web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs=request_kwargs))
                web3.eth.get_block_number()
                return web3
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(3)
                    continue
                raise Exception(f"Failed to Connect to RPC: {str(e)}")

    async def get_token_balance(self, address: str, rpc_url: str, contract_address: str, token_type: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, rpc_url, use_proxy)

            if token_type == "native":
                balance = web3.eth.get_balance(address)
                decimals = 18
            else:
                token_contract = web3.eth.contract(
                    address=web3.to_checksum_address(contract_address),
                    abi=self.ERC20_CONTRACT_ABI
                )
                balance = token_contract.functions.balanceOf(address).call()
                decimals = token_contract.functions.decimals().call()

            token_balance = balance / (10 ** decimals)
            return token_balance

        except Exception as e:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Message :{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
            )
            return None

    async def send_raw_transaction_with_retries(self, account, web3, tx, retries=5):
        for attempt in range(retries):
            try:
                signed_tx = web3.eth.account.sign_transaction(tx, account)
                raw_tx = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                tx_hash = web3.to_hex(raw_tx)
                return tx_hash
            except TransactionNotFound:
                pass
            except Exception as e:
                pass
            await asyncio.sleep(2 ** attempt)
        raise Exception("Transaction Hash Not Found After Maximum Retries")

    async def wait_for_receipt_with_retries(self, web3, tx_hash, retries=5):
        for attempt in range(retries):
            try:
                receipt = await asyncio.to_thread(web3.eth.wait_for_transaction_receipt, tx_hash, timeout=300)
                return receipt
            except TransactionNotFound:
                pass
            except Exception as e:
                pass
            await asyncio.sleep(2 ** attempt)
        raise Exception("Transaction Receipt Not Found After Maximum Retries")

    async def perform_bridge(self, account: str, address: str, rpc_url: str, dest_chain_id: int, src_address: str, amount: float, token_type: str, use_proxy: bool):
        try:
            web3 = await self.get_web3_with_check(address, rpc_url, use_proxy)
            contract_address = web3.to_checksum_address(src_address)
            abi = self.NATIVE_CONTRACT_ABI if token_type == "native" else self.ERC20_CONTRACT_ABI
            token_contract = web3.eth.contract(address=contract_address, abi=abi)

            amount_to_wei = web3.to_wei(amount, "ether")
            bridge_data = token_contract.functions.send(dest_chain_id, address, amount_to_wei)

            gas_params = {"from": address}
            if token_type == "native":
                gas_params["value"] = amount_to_wei

            estimated_gas = bridge_data.estimate_gas(gas_params)
            max_priority_fee = web3.to_wei(0.001, "gwei")
            max_fee = max_priority_fee

            tx_data = {
                "from": address,
                "gas": int(estimated_gas * 1.2),
                "maxFeePerGas": int(max_fee),
                "maxPriorityFeePerGas": int(max_priority_fee),
                "nonce": web3.eth.get_transaction_count(address, "pending"),
                "chainId": web3.eth.chain_id,
            }

            if token_type == "native":
                tx_data["value"] = amount_to_wei

            bridge_tx = bridge_data.build_transaction(tx_data)
            tx_hash = await self.send_raw_transaction_with_retries(account, web3, bridge_tx)
            receipt = await self.wait_for_receipt_with_retries(web3, tx_hash)

            block_number = receipt.blockNumber
            return tx_hash, block_number, amount_to_wei

        except Exception as e:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Message :{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
            )
            return None, None, None

    async def print_timer(self, type: str):
        for remaining in range(4, 1, -1):
            print(
                f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]{Style.RESET_ALL}"
                f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}"
                f"{Fore.BLUE + Style.BRIGHT}Wait For{Style.RESET_ALL}"
                f"{Fore.WHITE + Style.BRIGHT} {remaining} {Style.RESET_ALL}"
                f"{Fore.BLUE + Style.BRIGHT}Seconds For Next {type}...{Style.RESET_ALL}",
                end="\r",
                flush=True
            )
            await asyncio.sleep(1)

    def print_bridge_question(self):
        if os.path.exists(self.config_file) and self.bridge_count > 0 and self.min_bridge_amount > 0 and self.max_bridge_amount >= self.min_bridge_amount:
            self.log(
                f"{Fore.GREEN + Style.BRIGHT}Using saved config: "
                f"Bridge Count={self.bridge_count}, "
                f"Min Amount={self.min_bridge_amount}, "
                f"Max Amount={self.max_bridge_amount}{Style.RESET_ALL}"
            )
            return

        while True:
            try:
                bridge_count = int(input(f"{Fore.YELLOW + Style.BRIGHT}Bridge Transaction Count? -> {Style.RESET_ALL}").strip())
                if bridge_count > 0:
                    self.bridge_count = bridge_count
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Please enter positive number.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

        while True:
            try:
                min_bridge_amount = float(input(f"{Fore.YELLOW + Style.BRIGHT}Min Bridge Amount? -> {Style.RESET_ALL}").strip())
                if min_bridge_amount > 0:
                    self.min_bridge_amount = min_bridge_amount
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Amount must be greater than 0.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

        while True:
            try:
                max_bridge_amount = float(input(f"{Fore.YELLOW + Style.BRIGHT}Max Bridge Amount? -> {Style.RESET_ALL}").strip())
                if max_bridge_amount >= min_bridge_amount:
                    self.max_bridge_amount = max_bridge_amount
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Amount must be >= Min Bridge Amount.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number.{Style.RESET_ALL}")

        self.save_config()

    def get_proxy_settings(self):
        while True:
            try:
                print(f"{Fore.WHITE + Style.BRIGHT}1. Run With Proxyscrape Free Proxy{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}2. Run With Private Proxy{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}3. Run Without Proxy{Style.RESET_ALL}")
                choose = int(input(f"{Fore.BLUE + Style.BRIGHT}Choose [1/2/3] -> {Style.RESET_ALL}").strip())

                if choose in [1, 2, 3]:
                    proxy_type = (
                        "With Proxyscrape Free" if choose == 1 else
                        "With Private" if choose == 2 else
                        "Without"
                    )
                    print(f"{Fore.GREEN + Style.BRIGHT}Run {proxy_type} Proxy Selected.{Style.RESET_ALL}")
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Please enter either 1, 2 or 3.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number (1, 2 or 3).{Style.RESET_ALL}")

        rotate = False
        if choose in [1, 2]:
            while True:
                rotate = input(f"{Fore.BLUE + Style.BRIGHT}Rotate Invalid Proxy? [y/n] -> {Style.RESET_ALL}").strip()
                if rotate in ["y", "n"]:
                    rotate = rotate == "y"
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter 'y' or 'n'.{Style.RESET_ALL}")

        return choose, rotate

    async def submit_bridge_transfer(self, address: str, src_chain_id: int, dest_chain_id: int, src_address: str, dest_address: str, amount_to_wei: int, tx_hash: str, use_proxy: bool, retries=5):
        url = f"{self.BRIDGE_API}/bridge-transfer"
        data = json.dumps(self.generate_bridge_payload(address, src_chain_id, dest_chain_id, src_address, dest_address, amount_to_wei, tx_hash))
        headers = {
            **self.BRIDGE_HEADERS[address],
            "Content-Length": str(len(data)),
            "Content-Type": "application/json"
        }
        await asyncio.sleep(3)
        for attempt in range(retries):
            proxy_url = self.get_next_proxy_for_account(address) if use_proxy else None
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data, proxy=proxy, proxy_auth=proxy_auth, ssl=False) as response:
                        response.raise_for_status()
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}     Submit  :{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Failed {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )
        return None

    async def process_perform_bridge(self, account: str, address: str, rpc_url: str, src_chain_id: int, dest_chain_id: int, src_address: str, dest_address: str, amount: float, token_type: str, explorer: str, use_proxy: bool):
        tx_hash, block_number, amount_to_wei = await self.perform_bridge(account, address, rpc_url, dest_chain_id, src_address, amount, token_type, use_proxy)
        if tx_hash and block_number and amount_to_wei:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Status  :{Style.RESET_ALL}"
                f"{Fore.GREEN+Style.BRIGHT} Success {Style.RESET_ALL}"
            )
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Block   :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {block_number} {Style.RESET_ALL}"
            )
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Tx Hash :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {tx_hash} {Style.RESET_ALL}"
            )
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Explorer:{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {explorer}{tx_hash} {Style.RESET_ALL}"
            )

            submit = await self.submit_bridge_transfer(address, src_chain_id, dest_chain_id, src_address, dest_address, amount_to_wei, tx_hash, use_proxy)
            if submit:
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}     Submit  :{Style.RESET_ALL}"
                    f"{Fore.GREEN+Style.BRIGHT} Success  {Style.RESET_ALL}"
                )
        else:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}     Status  :{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} Perform On-Chain Failed {Style.RESET_ALL}"
            )

    async def process_option_6(self, account: str, address: str, use_proxy: bool):
        self.log(f"{Fore.CYAN+Style.BRIGHT}Bridge    :{Style.RESET_ALL}")
        bridge_sequence = self.get_bridge_sequence()
        for _ in range(self.bridge_count):
            for bridge_data in bridge_sequence:
                self.log(
                    f"{Fore.MAGENTA+Style.BRIGHT}   ● {Style.RESET_ALL}"
                    f"{Fore.GREEN+Style.BRIGHT}Bridge{Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT} {bridge_data['option']} {Style.RESET_ALL}"
                )

                option = bridge_data["option"]
                rpc_url = bridge_data["rpc_url"]
                explorer = bridge_data["explorer"]
                src_chain_id = bridge_data["src_chain_id"]
                dest_chain_id = bridge_data["dest_chain_id"]
                token_type = bridge_data["src_token"]["type"]
                src_ticker = bridge_data["src_token"]["ticker"]
                src_address = bridge_data["src_token"]["address"]
                dest_address = bridge_data["dest_token"]["address"]

                amount = round(random.uniform(self.min_bridge_amount, self.max_bridge_amount), 6)
                balance = await self.get_token_balance(address, rpc_url, src_address, token_type, use_proxy)

                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}     Pair    :{Style.RESET_ALL}"
                    f"{Fore.BLUE+Style.BRIGHT} {option} {Style.RESET_ALL}"
                )
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}     Balance :{Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT} {balance} {src_ticker} {Style.RESET_ALL}"
                )
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}     Amount  :{Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT} {amount} {src_ticker} {Style.RESET_ALL}"
                )

                if not balance or balance <= amount:
                    self.log(
                        f"{Fore.CYAN+Style.BRIGHT}     Status  :{Style.RESET_ALL}"
                        f"{Fore.YELLOW+Style.BRIGHT} Insufficient {src_ticker} Token Balance {Style.RESET_ALL}"
                    )
                    continue

                await self.process_perform_bridge(account, address, rpc_url, src_chain_id, dest_chain_id, src_address, dest_address, amount, token_type, explorer, use_proxy)
                await self.print_timer("Tx")

    async def main(self):
        while True:
            try:
                with open('accounts.txt', 'r') as file:
                    accounts = [line.strip() for line in file if line.strip()]

                self.clear_terminal()
                self.welcome()
                self.log(
                    f"{Fore.GREEN + Style.BRIGHT}Account's Total: {Style.RESET_ALL}"
                    f"{Fore.WHITE + Style.BRIGHT}{len(accounts)}{Style.RESET_ALL}"
                )

                self.print_bridge_question()
                use_proxy_choice, rotate_proxy = self.get_proxy_settings()

                if use_proxy_choice in [1, 2]:
                    await self.load_proxies(use_proxy_choice)

                separator = "=" * 25
                for account in accounts:
                    if account:
                        address = self.generate_address(account)
                        self.log(
                            f"{Fore.CYAN + Style.BRIGHT}{separator}[{Style.RESET_ALL}"
                            f"{Fore.WHITE + Style.BRIGHT} {self.mask_account(address)} {Style.RESET_ALL}"
                            f"{Fore.CYAN + Style.BRIGHT}]{separator}{Style.RESET_ALL}"
                        )

                        if not address:
                            self.log(
                                f"{Fore.CYAN+Style.BRIGHT}Status    :{Style.RESET_ALL}"
                                f"{Fore.RED+Style.BRIGHT} Invalid Private Key or Libraries Version Not Supported {Style.RESET_ALL}"
                            )
                            continue

                        user_agent = FakeUserAgent().random
                        self.BRIDGE_HEADERS[address] = {
                            "Accept": "application/json, text/plain, */*",
                            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                            "Origin": "https://bridge.prod.gokite.ai",
                            "Referer": "https://bridge.prod.gokite.ai/",
                            "Sec-Fetch-Dest": "empty",
                            "Sec-Fetch-Mode": "cors",
                            "Sec-Fetch-Site": "same-site",
                            "User-Agent": user_agent
                        }

                        await self.process_option_6(account, address, use_proxy_choice in [1, 2])
                        await asyncio.sleep(3)

                self.log(f"{Fore.CYAN + Style.BRIGHT}={Style.RESET_ALL}"*72)
                seconds = 8 * 60 * 60
                while seconds > 0:
                    formatted_time = self.format_seconds(seconds)
                    print(
                        f"{Fore.CYAN+Style.BRIGHT}[ Wait for{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} {formatted_time} {Style.RESET_ALL}"
                        f"{Fore.CYAN+Style.BRIGHT}... ]{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} | {Style.RESET_ALL}"
                        f"{Fore.BLUE+Style.BRIGHT}All Accounts Have Been Processed. Restarting in {formatted_time}...{Style.RESET_ALL}",
                        end="\r"
                    )
                    await asyncio.sleep(1)
                    seconds -= 1

            except FileNotFoundError:
                self.log(f"{Fore.RED}File 'accounts.txt' Not Found.{Style.RESET_ALL}")
                return
            except (Exception, ValueError) as e:
                self.log(f"{Fore.RED+Style.BRIGHT}Error: {e}{Style.RESET_ALL}")
                raise e

if __name__ == "__main__":
    try:
        bot = KiteAi()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print(
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().astimezone(wib).strftime('%x %X %Z')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}"
            f"{Fore.RED + Style.BRIGHT}[ EXIT ] Kite Ai - Bridge BOT{Style.RESET_ALL}"
            )
