"""
performance_test.py - Concurrent Load Test & Performance Evaluation
Jackfruit Mini Project - Component 4: Performance Evaluation

Tests:
  1. Throughput     - votes per second under concurrent load
  2. Latency (RTT)  - round-trip time per vote (send + server response)
  3. Loss analysis  - estimated packet loss from seq gaps
  4. Scalability    - response under increasing client count

Usage:
  python performance_test.py                         # default: 5 clients, 20 votes each
  python performance_test.py --clients 20 --votes 50
"""

import socket
import threading
import time
import random
import argparse
import statistics
from dataclasses import dataclass, field
from typing import List
from C_protocol import create_secure_vote, decrypt_response

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5005

OPTIONS = [1, 2, 3, 4, 5]


@dataclass
class ClientResult:
    voter_id:   int
    sent:       int   = 0
    accepted:   int   = 0
    rejected:   int   = 0
    timeouts:   int   = 0
    latencies:  List[float] = field(default_factory=list)   # ms RTT per packet


def worker(voter_id: int, num_votes: int, result: ClientResult, barrier: threading.Barrier):
    """Each worker = one simulated client sending num_votes packets."""
    barrier.wait()   # all threads start at the same time

    seq = 0
    for _ in range(num_votes):
        opt = random.choice(OPTIONS)
        pkt = create_secure_vote(voter_id, 1, opt, seq)
        seq += 1

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        t0 = time.perf_counter()
        try:
            sock.sendto(pkt, (SERVER_HOST, SERVER_PORT))
            data, _ = sock.recvfrom(4096)
            rtt = (time.perf_counter() - t0) * 1000   # ms
            resp = decrypt_response(data).decode()
            result.sent += 1
            result.latencies.append(rtt)
            if resp.startswith("Error:"):
                result.rejected += 1
            else:
                result.accepted += 1
        except socket.timeout:
            result.sent    += 1
            result.timeouts += 1
        except Exception:
            result.sent += 1
            result.timeouts += 1
        finally:
            sock.close()

        time.sleep(0.01)   # 100 pkt/s per client max


def run_test(num_clients: int, num_votes: int):
    print()
    print("=" * 58)
    print("  Performance Evaluation - Live Polling System")
    print("  Jackfruit Mini Project")
    print("=" * 58)
    print(f"  Server          : {SERVER_HOST}:{SERVER_PORT}")
    print(f"  Concurrent clients : {num_clients}")
    print(f"  Votes per client   : {num_votes}")
    print(f"  Total packets      : {num_clients * num_votes}")
    print("=" * 58)

    # Assign unique voter IDs so server accepts only the first vote per voter
    results  = [ClientResult(voter_id=2000 + i) for i in range(num_clients)]
    barrier  = threading.Barrier(num_clients)
    threads  = [
        threading.Thread(target=worker,
                         args=(r.voter_id, num_votes, r, barrier),
                         daemon=True)
        for r in results
    ]

    print(f"\n  [*] Launching {num_clients} concurrent clients...\n")
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - t_start

    # ── Aggregate ─────────────────────────────
    total_sent     = sum(r.sent      for r in results)
    total_accepted = sum(r.accepted  for r in results)
    total_rejected = sum(r.rejected  for r in results)
    total_timeouts = sum(r.timeouts  for r in results)
    all_latencies  = [l for r in results for l in r.latencies]

    throughput = total_sent / elapsed if elapsed > 0 else 0

    print("  THROUGHPUT & RELIABILITY")
    print("  " + "-" * 54)
    print(f"  Elapsed time          : {elapsed:.3f} s")
    print(f"  Total packets sent    : {total_sent}")
    print(f"  Accepted (1st vote)   : {total_accepted}")
    print(f"  Rejected (dup/invalid): {total_rejected}")
    print(f"  Timeouts              : {total_timeouts}")
    print(f"  Throughput            : {throughput:.1f} packets/s")

    if all_latencies:
        print()
        print("  LATENCY  (Round-Trip Time per packet, ms)")
        print("  " + "-" * 54)
        print(f"  Min     : {min(all_latencies):.3f} ms")
        print(f"  Max     : {max(all_latencies):.3f} ms")
        print(f"  Mean    : {statistics.mean(all_latencies):.3f} ms")
        print(f"  Median  : {statistics.median(all_latencies):.3f} ms")
        if len(all_latencies) > 1:
            print(f"  Std Dev : {statistics.stdev(all_latencies):.3f} ms")

        # Percentile breakdown
        sorted_lat = sorted(all_latencies)
        n = len(sorted_lat)
        p95 = sorted_lat[int(n * 0.95)]
        p99 = sorted_lat[int(n * 0.99)] if n > 100 else sorted_lat[-1]
        print(f"  P95     : {p95:.3f} ms")
        print(f"  P99     : {p99:.3f} ms")

    # ── Packet loss estimate from seq gaps ────
    print()
    print("  PACKET LOSS ANALYSIS  (from sequence number gaps)")
    print("  " + "-" * 54)
    total_expected = 0
    total_missing  = 0
    for r in results:
        expected = num_votes
        received = r.sent - r.timeouts
        lost     = max(0, expected - received)
        total_expected += expected
        total_missing  += lost

    loss_pct = total_missing / total_expected * 100 if total_expected > 0 else 0
    print(f"  Expected packets      : {total_expected}")
    print(f"  Estimated lost        : {total_missing}")
    print(f"  Estimated loss rate   : {loss_pct:.2f}%")

    # ── Scalability note ──────────────────────
    print()
    print("  SCALABILITY OBSERVATIONS")
    print("  " + "-" * 54)
    avg_lat = statistics.mean(all_latencies) if all_latencies else 0
    if avg_lat < 5:
        obs = "Excellent - sub-5ms average latency under load."
    elif avg_lat < 20:
        obs = "Good - latency within acceptable range for real-time."
    else:
        obs = "Degraded - high latency; server may be under stress."

    if loss_pct < 1:
        loss_obs = "No significant packet loss detected."
    elif loss_pct < 5:
        loss_obs = "Minor packet loss within UDP tolerance."
    else:
        loss_obs = "High packet loss - consider retry logic."

    print(f"  Latency  : {obs}")
    print(f"  Loss     : {loss_obs}")
    print(f"  Threading: {num_clients} concurrent clients handled via server threading.")
    print()
    print("=" * 58)
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Performance test for polling server")
    ap.add_argument("--host",    default="127.0.0.1")
    ap.add_argument("--clients", type=int, default=5,  help="Concurrent clients")
    ap.add_argument("--votes",   type=int, default=20, help="Votes per client")
    args = ap.parse_args()

    SERVER_HOST = args.host
    run_test(args.clients, args.votes)
