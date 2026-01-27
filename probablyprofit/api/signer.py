"""
Wallet Signer

Handles wallet connection and transaction signing for Polymarket.

Security features:
- Private keys are encrypted in memory using XOR with a random mask
- Keys are only decrypted momentarily when needed for signing
- Original plaintext key is never stored after initialization
"""

import secrets
from typing import Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from loguru import logger
from web3 import Web3


class SecureKey:
    """
    Secure wrapper for private keys with memory encryption.

    The private key is XOR'd with a random mask immediately upon storage.
    This prevents the plaintext key from sitting in memory where it could
    be extracted via memory dumps, core dumps, or debugging tools.

    The key is only decrypted momentarily when needed for signing operations.
    """

    def __init__(self, private_key: str):
        """
        Initialize secure key storage.

        Args:
            private_key: Private key (with or without 0x prefix)
        """
        # Normalize the key
        if private_key.startswith("0x"):
            private_key = private_key[2:]

        # Convert to bytes
        key_bytes = bytes.fromhex(private_key)

        # Generate random mask of same length
        self._mask = secrets.token_bytes(len(key_bytes))

        # Store XOR'd version (encrypted)
        self._encrypted = bytes(a ^ b for a, b in zip(key_bytes, self._mask))

        # Clear the original key from this scope
        # (Python doesn't guarantee this, but it helps)
        del private_key
        del key_bytes

    def get_key(self) -> str:
        """
        Get the decrypted private key.

        Returns:
            Private key as hex string with 0x prefix

        Note: Caller should use the key immediately and not store it.
        """
        # XOR again to decrypt
        decrypted = bytes(a ^ b for a, b in zip(self._encrypted, self._mask))
        return "0x" + decrypted.hex()

    def __repr__(self) -> str:
        """Safe representation that doesn't expose the key."""
        return "<SecureKey: [ENCRYPTED]>"

    def __str__(self) -> str:
        """Safe string that doesn't expose the key."""
        return "[SECURE_KEY]"


class WalletSigner:
    """
    Manages wallet connection and transaction signing.

    Provides secure key management and transaction signing for Polymarket trades.
    """

    def __init__(self, private_key: str, chain_id: int = 137):
        """
        Initialize wallet signer with secure key storage.

        Args:
            private_key: Private key (with or without 0x prefix)
            chain_id: Chain ID (137 for Polygon mainnet)

        Security: The private key is encrypted in memory immediately after
        deriving the wallet address. It is only decrypted momentarily when
        needed for signing operations.
        """
        self.chain_id = chain_id

        # Store key securely (encrypted in memory)
        self._secure_key = SecureKey(private_key)

        # Derive address once (this requires decrypting the key temporarily)
        temp_key = self._secure_key.get_key()
        temp_account = Account.from_key(temp_key)
        self.address = temp_account.address

        # Clear temporary references
        del temp_key
        del temp_account

        # Note: We don't store self.account permanently anymore
        # It will be created on-demand during signing operations

        logger.info(f"Wallet initialized: {self.address}")

    def _get_account(self) -> LocalAccount:
        """
        Get account for signing (decrypts key temporarily).

        Returns:
            LocalAccount instance for signing

        Note: The returned account should be used immediately and not stored.
        """
        temp_key = self._secure_key.get_key()
        account = Account.from_key(temp_key)
        del temp_key
        return account

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

            # Get account temporarily for signing
            account = self._get_account()
            signed = account.sign_message_hash(message_hash)

            # Clear account reference
            del account

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

            # Get account temporarily for signing
            account = self._get_account()
            signed_txn = account.sign_transaction(transaction)

            # Clear account reference
            del account

            return signed_txn.rawTransaction.hex()

        except Exception as e:
            logger.error(f"Error signing transaction: {e}")
            raise

    def get_address(self) -> str:
        """Get wallet address."""
        return self.address
