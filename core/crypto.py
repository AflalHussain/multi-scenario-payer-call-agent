import os
from cryptography.fernet import Fernet

class PayerCrypto:
    """
    Utility for encrypting and decrypting sensitive data (like member IDs)
    before it crosses the payer boundary.
    
    In a real production environment, the shared key would be securely
    injected via a vault or environment variable.
    """
    
    # Generate a static key for the mock environment if one isn't provided
    _SHARED_KEY = os.environ.get("PAYER_SHARED_KEY", Fernet.generate_key().decode())
    _fernet = Fernet(_SHARED_KEY.encode())

    @classmethod
    def encrypt_member_id(cls, member_id: str) -> str:
        """Encrypt the member ID and wrap it in a token format."""
        encrypted = cls._fernet.encrypt(member_id.encode()).decode()
        return f"[ENC:{encrypted}]"

    @classmethod
    def decrypt_member_id(cls, token: str) -> str | None:
        """Extract and decrypt the member ID from a token."""
        if not token.startswith("[ENC:") or not token.endswith("]"):
            return None
            
        encrypted = token[5:-1]
        try:
            return cls._fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            return None
