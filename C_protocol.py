"""
protocol.py – Custom Vote Packet Format + Fernet (AES-128) Encryption
No SSL certificates required — shared key security mechanism.

UDP Payload (before encryption):
  Field      Type    Size   Description
  ─────────────────────────────────────
  voter_id   uint32  4 B    Unique voter identifier
  poll_id    uint32  4 B    Which poll / election
  option_id  uint32  4 B    Chosen candidate / option
  seq_num    uint32  4 B    Sequence number (duplicate detection)
  ─────────────────────────────────────
  Total                16 B (plaintext) → ~120 B after Fernet encryption
"""

import struct
from cryptography.fernet import Fernet

# Shared AES key (Fernet = AES-128-CBC + HMAC-SHA256)
# In production this would be exchanged via a secure channel.
SECRET_KEY = b'w1rO_zK0Y_vXG0d8_wA7g_jV4L_pQ1s_mN2b_vC3x_k='
cipher = Fernet(SECRET_KEY)

PACK_FMT = '!IIII'   # 4 × uint32 big-endian


def create_secure_vote(voter_id: int, poll_id: int,
                       option_id: int, seq_num: int) -> bytes:
    """Pack the vote fields into 16 bytes and encrypt with Fernet."""
    payload = struct.pack(PACK_FMT, voter_id, poll_id, option_id, seq_num)
    return cipher.encrypt(payload)


def parse_secure_vote(encrypted_data: bytes):
    """Decrypt and unpack → (voter_id, poll_id, option_id, seq_num).
    Raises InvalidToken if the data is tampered or uses the wrong key."""
    decrypted = cipher.decrypt(encrypted_data)
    return struct.unpack(PACK_FMT, decrypted)


def encrypt_response(message_bytes: bytes) -> bytes:
    """Encrypt a server response message."""
    return cipher.encrypt(message_bytes)


def decrypt_response(encrypted_message: bytes) -> bytes:
    """Decrypt a server response message."""
    return cipher.decrypt(encrypted_message)
