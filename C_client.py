"""
client.py - Live Polling and Voting System (Client)
Security: Fernet AES-128-CBC + HMAC-SHA256
"""

import socket
import threading
import argparse
import os
from C_protocol import create_secure_vote, decrypt_response

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5005

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

# Shared: last results received (from vote response or broadcast)
last_results = {"text": None, "lock": threading.Lock()}


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║         LIVE POLLING SYSTEM              ║")
    print("  ║      Class Representative Election       ║")
    print("  ╚══════════════════════════════════════════╝")
    print()


def print_poll():
    print(f"  {POLL['question']}")
    print()
    for oid, oname in POLL["options"].items():
        print(f"    {oid}.  {oname}")
    print()


def print_results(text: str):
    """Parse and display the tally block from server response."""
    lines = text.strip().split("\n")
    # Find the tally block: lines starting from "Current Results"
    tally_lines = []
    in_tally = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Current Results") or in_tally:
            in_tally = True
            if stripped and not stripped.startswith("-----"):
                tally_lines.append(stripped)

    if not tally_lines:
        return

    print()
    print("  ┌──────────────────────────────────────────────┐")
    for line in tally_lines:
        display = line[:46]
        print(f"  │  {display:<46}│")
    print("  └──────────────────────────────────────────────┘")
    print()


def send_vote(voter_id: int, option_id: int, seq_num: int):
    """Send encrypted UDP vote on a dedicated socket. Returns (next_seq, response_str | None)."""
    pkt = create_secure_vote(voter_id, 1, option_id, seq_num)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)
    try:
        sock.sendto(pkt, (SERVER_HOST, SERVER_PORT))
        data, _ = sock.recvfrom(4096)
        resp = decrypt_response(data).decode()
        return seq_num + 1, resp
    except socket.timeout:
        return seq_num + 1, None
    except OSError as e:
        return seq_num + 1, f"Error: Network error - {e}"
    finally:
        sock.close()


def broadcast_listener(voter_id: int):
    """
    Listen on a dedicated socket for periodic server broadcasts.
    When a broadcast arrives, update last_results and print a notification.
    """
    bsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    bsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bsock.bind(('', 0))    # any free port
    bsock.settimeout(None)

    # Send a silent ping so server learns this socket's address for broadcasts
    try:
        ping = create_secure_vote(voter_id, 0, 0, 9999)
        bsock.sendto(ping, (SERVER_HOST, SERVER_PORT))
    except Exception:
        pass

    while True:
        try:
            data, _ = bsock.recvfrom(4096)
            msg = decrypt_response(data).decode()
            if "[Live Update" in msg:
                with last_results["lock"]:
                    last_results["text"] = msg
                # Print a non-intrusive notification below the prompt
                print("\n  [Live update received — press Enter to view]")
        except Exception:
            pass


def show_live_results():
    with last_results["lock"]:
        text = last_results["text"]
    if text:
        print_results(text)
    else:
        print()
        print("  No live update received yet.")
        print()


def start_client(voter_id: int):
    clear()
    print_banner()
    print(f"  Welcome, Voter #{voter_id}")
    print(f"  {'─'*44}")
    print()
    print_poll()

    # Start broadcast listener in background
    threading.Thread(target=broadcast_listener, args=(voter_id,),
                     daemon=True).start()

    seq_num  = 0
    has_voted = False

    while True:
        try:
            if has_voted:
                print("  Your vote has been recorded.")
                print()
                cmd = input("  Press Enter to see live results, or q to quit: ").strip().lower()
                if cmd == "q":
                    print()
                    print("  Thank you for participating!")
                    print()
                    break
                show_live_results()
                continue

            raw = input("  Enter the number of your choice (1-5), or q to quit: ").strip()

            if raw.lower() == "q":
                print()
                print("  Exiting. Goodbye!")
                print()
                break

            if not raw.isdigit() or int(raw) not in POLL["options"]:
                print()
                print("  ✗  Please enter a valid number between 1 and 5.")
                print()
                continue

            opt       = int(raw)
            candidate = POLL["options"][opt]
            print()
            confirm = input(f"  You selected: {candidate}. Confirm? (y/n): ").strip().lower()
            print()

            if confirm != "y":
                print("  Vote cancelled.")
                print()
                print_poll()
                continue

            print("  Submitting your vote...")
            seq_num, resp = send_vote(voter_id, opt, seq_num)

            if resp is None:
                print()
                print("  ✗  Could not reach the server. Please check your connection.")
                print()
                continue

            if resp.startswith("Error:"):
                msg = resp.replace("Error: ", "")
                print(f"  ✗  {msg}")
                print()
                if "already voted" in resp:
                    has_voted = True
                continue

            # ── Success ────────────────────────
            print()
            print(f"  ✓  Your vote for {candidate} has been recorded successfully.")
            has_voted = True
            # Store result for later viewing and display immediately
            with last_results["lock"]:
                last_results["text"] = resp
            print_results(resp)

        except (EOFError, KeyboardInterrupt):
            print()
            print("  Exiting. Goodbye!")
            print()
            break


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Live Polling Client")
    ap.add_argument("--voter-id", type=int, default=None, help="Your voter ID")
    ap.add_argument("--host",     default="127.0.0.1",    help="Server IP address")
    args = ap.parse_args()

    SERVER_HOST = args.host

    print_banner()
    if args.voter_id is None:
        try:
            print("  Please enter your Voter ID to continue.")
            print()
            vid = int(input("  Voter ID: ").strip())
        except ValueError:
            print()
            print("  Invalid ID. Voter ID must be a number.")
            exit(1)
    else:
        vid = args.voter_id

    start_client(vid)
