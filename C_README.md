# Live Polling and Voting System

**Jackfruit Mini Project – CN Socket Programming**  
**Language:** Python 3 &nbsp;|&nbsp; **Protocol:** UDP + Fernet (AES-128) &nbsp;|&nbsp; **No SSL certificates required**

---

## Problem Statement

Design and implement a real-time polling system where multiple clients submit votes over **UDP sockets**. The server must aggregate results reliably, detect duplicates, enforce one-vote-per-voter, and broadcast live results to all connected clients — all secured without SSL certificates using symmetric encryption.

**Objectives:**

- Custom UDP packet format with sequence numbering
- Fernet (AES-128-CBC + HMAC-SHA256) encryption on every packet
- Duplicate vote detection at two levels: voter ID and sequence number
- Support for multiple concurrent clients using threading
- Periodic live result broadcasts to all clients
- Performance evaluation under realistic concurrent load

---

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              POLL SERVER                     │
                    │           (UDP Port 5005)                    │
                    │                                              │
                    │  ┌───────────┐   ┌──────────────────────┐   │
                    │  │ Broadcast │   │  Receive Loop        │   │
                    │  │ Thread    │   │  recvfrom()          │   │
                    │  │ (every10s)│   │  → spawn thread      │   │
                    │  └─────┬─────┘   └──────────┬───────────┘   │
                    │        │                     │               │
                    │        │          ┌──────────▼───────────┐  │
                    │        │          │   handle_packet()    │  │
                    │        │          │  1. Size check       │  │
                    │        │          │  2. Fernet decrypt   │  │
                    │        │          │  3. Already voted?   │  │
                    │        │          │  4. Seq dup check    │  │
                    │        │          │  5. Option valid?    │  │
                    │        │          │  6. Accept + tally   │  │
                    │        │          └──────────┬───────────┘  │
                    │        │                     │               │
                    │        │          ┌──────────▼───────────┐  │
                    │        └─────────►│   Poll State (Lock)  │  │
                    │                   │  votes{}              │  │
                    │                   │  voted_ids{}          │  │
                    │                   │  seen_seqs{}          │  │
                    │                   │  pkt_stats{}          │  │
                    │                   └──────────────────────┘  │
                    └──────────────────────────────────────────┬───┘
                                      ▲  Encrypted UDP         │
              ┌───────────────────────┘  Packets               │ Encrypted
              │                                                 │ Broadcasts
    ┌─────────┴──────────┐                          ┌──────────▼──────────┐
    │     CLIENT A        │                          │     CLIENT B         │
    │  voter_id = 101     │                          │  voter_id = 202      │
    │                     │                          │                      │
    │  Vote socket        │                          │  Vote socket         │
    │  create_secure_vote │                          │  create_secure_vote  │
    │  → struct.pack()    │                          │  → struct.pack()     │
    │  → Fernet.encrypt() │                          │  → Fernet.encrypt()  │
    │                     │                          │                      │
    │  sendto() ──────────┼──── Encrypted UDP ───────┼──────────────────    │
    │  recvfrom() ◄───────┼──── Encrypted Response ──┤                      │
    │                     │                          │                      │
    │  Broadcast socket   │                          │  Broadcast socket    │
    │  (separate port)    │◄─── Live Updates ────────┤  (separate port)     │
    └─────────────────────┘                          └──────────────────────┘

                    ┌──────────────────────────────────────┐
                    │     performance_test.py              │
                    │   N threads × M votes concurrently   │
                    │   Measures: throughput, RTT, loss%   │
                    └──────────────────────────────────────┘
```

### Communication Flow

```
CLIENT                                          SERVER
  │                                               │
  │  create_secure_vote(voter_id, 1,              │
  │       option_id, seq_num)                     │
  │  → struct.pack (16 bytes plaintext)           │
  │  → Fernet.encrypt (~120 bytes)                │
  │                                               │
  │──────── Encrypted UDP Packet ────────────────►│
  │                                               ├── size check (edge case)
  │                                               ├── Fernet.decrypt + HMAC verify
  │                                               ├── voter_id already voted?
  │                                               ├── seq_num duplicate?
  │                                               ├── option_id valid?
  │                                               └── tally + respond
  │                                               │
  │◄──── Encrypted Response + Current Tally ──────│
  │                                               │
  │              (every 10 seconds)               │
  │◄──── Encrypted Broadcast (live results) ──────│
  │      pushed to ALL known client addresses     │
```

---

## UDP Packet Format

```
 Offset  Field      Type    Bytes   Description
 ──────────────────────────────────────────────────
  0      voter_id   uint32   4      Unique voter identifier
  4      poll_id    uint32   4      Poll number (= 1)
  8      option_id  uint32   4      Chosen candidate (1–5)
  12     seq_num    uint32   4      Per-voter sequence number
 ──────────────────────────────────────────────────
         Plaintext           16 B  →  ~120 B after Fernet encryption
```

---

## Security Mechanism

| Property        | Implementation                          |
| --------------- | --------------------------------------- |
| Confidentiality | Fernet (AES-128-CBC)                    |
| Integrity       | HMAC-SHA256 (built into Fernet)         |
| Tamper detect   | `InvalidToken` exception on bad packets |
| Replay resist   | Per-voter sequence number tracking      |
| One vote/voter  | voter_id set enforced server-side       |

> No SSL certificates required. Security is provided by a shared Fernet key.

---

## The Poll

```
  Question: Who should be the next Class Representative?

    [1]  Alice Johnson
    [2]  Bob Sharma
    [3]  Charlie Patel
    [4]  Diana Nair
    [5]  Edward Kumar
```

---

## Setup & Run

### 1. Install dependency

```bash
pip install cryptography
```

### 2. Start the server

```bash
python server.py
```

### 3. Start one or more clients (each in a new terminal)

```bash
python client.py
# Enter Voter ID when prompted

python client.py --voter-id 42          # pass ID directly
python client.py --host 192.168.1.10    # connect to remote server
```

### 4. Run performance test (server must be running)

```bash
python performance_test.py
python performance_test.py --clients 20 --votes 50
```

---

## Performance Evaluation

Sample output from `python performance_test.py --clients 8 --votes 10`:

```
  THROUGHPUT & RELIABILITY
  Elapsed time          : 0.38 s
  Total packets sent    : 80
  Accepted (1st vote)   : 8
  Rejected (dup/invalid): 72
  Throughput            : 209.8 packets/s

  LATENCY  (Round-Trip Time per packet, ms)
  Min     : 0.786 ms
  Max     : 66.280 ms
  Mean    : 13.655 ms
  Median  : 2.586 ms
  P95     : 65.225 ms

  PACKET LOSS ANALYSIS
  Estimated loss rate   : 0.00%

  SCALABILITY OBSERVATIONS
  Latency  : Good - latency within acceptable range for real-time.
  Loss     : No significant packet loss detected.
  Threading: 8 concurrent clients handled via server threading.
```

**Observations:**

- Median RTT of ~2.6ms demonstrates low-latency UDP performance
- P95 spike to ~65ms observed when all threads start simultaneously (thread scheduling)
- 0% packet loss on localhost; in real networks UDP loss is expected and handled via duplicate detection
- Server threading allows true concurrent handling — one thread per incoming packet

---

## Edge Cases Handled

| Edge Case                           | Handling                                                           |
| ----------------------------------- | ------------------------------------------------------------------ |
| Same voter votes twice              | Rejected with clear error message; voter_id checked first          |
| Duplicate UDP packet (same seq)     | Detected via per-voter sequence number set                         |
| Tampered / corrupted packet         | Fernet raises `InvalidToken`; dropped silently with error response |
| Malformed packet (too short)        | Size check before decrypt; error response sent                     |
| Invalid option number               | Validated server-side before tallying                              |
| Client disconnects abruptly         | UDP is connectionless; server simply stops receiving; no crash     |
| Unreachable client during broadcast | `OSError` caught; client removed from broadcast list               |
| Network error on client             | Caught as `OSError`; user shown friendly error message             |

---

## File Structure

```
live-polling-system/
├── protocol.py          – Packet format + Fernet encrypt/decrypt
├── server.py            – UDP server, threading, broadcasts, edge cases
├── client.py            – Interactive voting client with live update display
├── performance_test.py  – Concurrent load test + latency/throughput metrics
└── requirements.txt     – cryptography (only dependency)
```

---

## Design Choices

| Decision                        | Rationale                                                                   |
| ------------------------------- | --------------------------------------------------------------------------- |
| UDP over TCP                    | Matches project spec; lower overhead; appropriate for fire-and-forget votes |
| Fernet over SSL                 | No certificate infrastructure needed; provides AES + HMAC in one primitive  |
| Thread-per-packet               | Simple concurrency model; handles multiple clients without blocking         |
| Dedicated broadcast socket      | Prevents race condition between vote response and broadcast listener        |
| Voter ID check before seq check | Gives user the correct, meaningful error message first                      |

---

## Rubric Coverage

| Component                         | Marks  | Implementation                                                             |
| --------------------------------- | ------ | -------------------------------------------------------------------------- |
| Problem Definition & Architecture | 6      | Problem statement, objectives, system + flow diagrams above                |
| Core Socket Implementation        | 8      | `socket()`, `bind()`, `sendto()`, `recvfrom()` — no framework              |
| Feature Implementation (D1)       | 8      | Multiple clients (threading), Fernet security, dup detection, broadcasts   |
| Performance Evaluation            | 7      | `performance_test.py` — throughput, RTT, P95/P99, loss%, scalability notes |
| Optimisation & Fixes              | 5      | Check order fix, edge case table, OSError handling, broadcast cleanup      |
| Final Demo + GitHub               | 6      | This README, setup steps, design rationale, usage instructions             |
| **Total**                         | **40** |                                                                            |
