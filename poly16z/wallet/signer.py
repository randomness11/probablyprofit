"""
Wallet Signer

Handles wallet connection and transaction signing for Polymarket.
"""

from typing import Optional
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from loguru import logger


class WalletSigner:
    """
    Manages wallet connection and transaction signing.

    Provides secure key management and transaction signing for Polymarket trades.
    """

    def __init__(self, private_key: str, chain_id: int = 137):
        """
        Initialize wallet signer.

        Args:
            private_key: Private key (with or without 0x prefix)
            chain_id: Chain ID (137 for Polygon mainnet)
        """
        self.chain_id = chain_id

        # Ensure private key has 0x prefix
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"

        # Create account from private key
        self.account: LocalAccount = Account.from_key(private_key)
        self.address = self.account.address

        logger.info(f"Wallet initialized: {self.address}")

    def sign_message(self, message: str) -> str:
        """
        Sign a message.

        Args:
            message: Message to sign

        Returns:
            Signed message signature
        """
        try:
            # Encode message
            encoded_message = f"\x19Ethereum Signed Message:\n{len(message)}{message}"
            message_hash = Web3.keccak(text=encoded_message)

            # Sign
            signed = self.account.sign_message_hash(message_hash)
            return signed.signature.hex()

        except Exception as e:
            logger.error(f"Error signing message: {e}")
            raise

    def sign_transaction(self, transaction: dict) -> str:
        """
        Sign a transaction.

        Args:
            transaction: Transaction dict

        Returns:
            Signed transaction hex
        """
        try:
            # Add chain ID
            transaction["chainId"] = self.chain_id

            # Sign transaction
            signed_txn = self.account.sign_transaction(transaction)
            return signed_txn.rawTransaction.hex()

        except Exception as e:
            logger.error(f"Error signing transaction: {e}")
            raise

    def get_address(self) -> str:
        """Get wallet address."""
        return self.address
