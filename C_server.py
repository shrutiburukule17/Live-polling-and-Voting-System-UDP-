"""
server.py - Live Polling and Voting System (Server)
Security : Fernet AES-128-CBC + HMAC-SHA256
Handles  : multiple concurrent clients, edge cases, broadcasts
"""

import socket
import threading
import time
from collections import defaultdict
from datetime import datetime
from C_protocol import parse_secure_vote, encrypt_response

HOST             = '0.0.0.0'
PORT             = 5005
BROADCAST_INTERVAL = 10   # seconds

POLL = {
    "question": "Who should be the next Class Representative?",
    "options": {
        1: "Alice Johnson",
        2: "Bob Sharma",
        3: "Charlie Patel",
        4: "Diana Nair",
        5: "Edward Kumar",
    },
}

# ── Shared state (all access under lock) ──────
votes         = defaultdict(int)
voted_ids     = set()
seen_seqs     = defaultdict(set)
pkt_stats     = defaultdict(lambda: {"received": 0, "duplicates": 0, "invalid": 0})
known_clients = set()
lock          = threading.Lock()

# ── Performance counters ──────────────────────
perf = {"total_packets": 0, "accepted": 0, "rejected": 0, "start_time": time.time()}


def tally_text() -> str:
    total = sum(votes.values())
    lines = [
        f"Current Results  -  {POLL['question']}",
        f"Total votes cast: {total}",
        f"-------------------------------------",
    ]
    for opt_id, opt_name in POLL["options"].items():
        n = votes[opt_id]
        lines.append(f"[{opt_id}] {opt_name:<18}  {n} vote(s)")
    lines.append(f"-------------------------------------")
    return "\n".join(lines)


# ── Periodic broadcast to all known clients ───
def broadcast_thread(sock):
    while True:
        time.sleep(BROADCAST_INTERVAL)
        with lock:
            targets = list(known_clients)
        if not targets:
            continue
        ts  = datetime.now().strftime("%H:%M:%S")
        msg = ("[Live Update - " + ts + "]\n" + tally_text()).encode()
        enc = encrypt_response(msg)
        dead = []
        for addr in targets:
            try:
                sock.sendto(enc, addr)
            except OSError:
                dead.append(addr)   # remove unreachable clients
        if dead:
            with lock:
                for addr in dead:
                    known_clients.discard(addr)


# ── Per-packet handler (runs in its own thread) ──
def handle_packet(sock, data, addr):
    # Register client address for broadcasts
    with lock:
        known_clients.add(addr)
        perf["total_packets"] += 1

    # ── Edge case: empty / too-short packet ───
    if not data or len(data) < 16:
        print(f"  [!] Malformed packet from {addr} (size={len(data)})")
        with lock:
            perf["rejected"] += 1
        try:
            sock.sendto(encrypt_response(b"Error: Malformed packet."), addr)
        except OSError:
            pass
        return

    # ── Decrypt + unpack ──────────────────────
    try:
        voter_id, poll_id, option_id, seq_num = parse_secure_vote(data)
    except Exception as e:
        print(f"  [!] Tampered/invalid packet from {addr}: {type(e).__name__}")
        with lock:
            perf["rejected"] += 1
        try:
            sock.sendto(encrypt_response(b"Error: Invalid or tampered packet."), addr)
        except OSError:
            pass
        return

    with lock:
        pkt_stats[voter_id]["received"] += 1

        # ── Priority 1: already voted ─────────
        if voter_id in voted_ids:
            pkt_stats[voter_id]["duplicates"] += 1
            perf["rejected"] += 1
            print(f"  [-]   Rejected: voter={voter_id} already voted")
            try:
                sock.sendto(encrypt_response(
                    b"Error: You have already voted. Only one vote per voter is allowed."), addr)
            except OSError:
                pass
            return

        # ── Priority 2: seq-level dup (network retransmit) ──
        if seq_num in seen_seqs[voter_id]:
            pkt_stats[voter_id]["duplicates"] += 1
            perf["rejected"] += 1
            print(f"  [DUP]  voter={voter_id}  seq={seq_num}")
            try:
                sock.sendto(encrypt_response(b"Error: Duplicate packet detected."), addr)
            except OSError:
                pass
            return
        seen_seqs[voter_id].add(seq_num)

        # ── Priority 3: invalid option ────────
        if option_id not in POLL["options"]:
            perf["rejected"] += 1
            try:
                sock.sendto(encrypt_response(b"Error: Invalid option. Choose 1-5."), addr)
            except OSError:
                pass
            return

        # ── Accept vote ───────────────────────
        votes[option_id] += 1
        voted_ids.add(voter_id)
        opt_name = POLL["options"][option_id]
        total    = sum(votes.values())
        perf["accepted"] += 1
        print(f"  [+]   Vote accepted: voter={voter_id}  "
              f"option={option_id} ({opt_name})  total={total}")
        

    # Send confirmation with current tally (outside lock)
    resp = ("Vote accepted! You voted for: " + opt_name + "\n" + tally_text()).encode()
    try:
        sock.sendto(encrypt_response(resp), addr)
    except OSError as e:
        print(f"  [!] Failed to send response to {addr}: {e}")


# ── Main ──────────────────────────────────────
def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))

    threading.Thread(target=broadcast_thread, args=(sock,),
                     daemon=True, name="Broadcast").start()

    print("=" * 52)
    print("  Live Polling Server  -  Jackfruit Mini Project")
    print("=" * 52)
    print(f"  UDP port  : {PORT}")
    print(f"  Security  : Fernet (AES-128 + HMAC-SHA256)")
    print(f"  Broadcast : every {BROADCAST_INTERVAL}s")
    print("=" * 52)
    print(f"\n  Poll: {POLL['question']}")
    for oid, oname in POLL["options"].items():
        print(f"    [{oid}] {oname}")
    print(f"\n  [*] Waiting for votes...\n")

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            threading.Thread(target=handle_packet,
                             args=(sock, data, addr), daemon=True).start()
        except OSError as e:
            print(f"  [!] Socket error: {e}")
        except Exception as e:
            print(f"  [!] Unexpected server error: {e}")


if __name__ == "__main__":
    start_server()
