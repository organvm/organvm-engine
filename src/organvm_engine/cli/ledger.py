"""Ledger CLI commands — the Testament Protocol's native hash chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_DEFAULT_CHAIN_PATH = Path.home() / ".organvm" / "testament" / "chain.jsonl"


def _chain_path(args: argparse.Namespace) -> Path:
    """Resolve chain path from args or default."""
    raw = getattr(args, "chain_path", None)
    return Path(raw) if raw else _DEFAULT_CHAIN_PATH


def cmd_ledger_genesis(args: argparse.Namespace) -> int:
    """Initialize the Testament Chain with a genesis event."""
    from organvm_engine.events.spine import EventSpine

    path = _chain_path(args)
    if path.is_file() and path.stat().st_size > 0:
        print(f"  Chain already exists at {path}")
        print("  Genesis can only be called once. The chain is immutable.")
        return 1

    spine = EventSpine(path)
    record = spine.emit(
        event_type="testament.genesis",
        entity_uid="",
        source_organ="META-ORGANVM",
        source_repo="organvm-engine",
        actor="human:genesis",
        payload={
            "message": (
                "The Testament Chain begins. Every mutation witnessed. "
                "Every state traceable. The system remembers."
            ),
        },
    )

    print("\n  Testament Chain Genesis")
    print(f"  {'=' * 48}")
    print(f"  Event ID:  {record.event_id}")
    print(f"  Sequence:  {record.sequence}")
    print(f"  Hash:      {record.hash}")
    print(f"  Path:      {path}")
    print("\n  The chain has begun.\n")
    return 0


def cmd_ledger_status(args: argparse.Namespace) -> int:
    """Show Testament Chain status."""
    from organvm_engine.ledger.chain import verify_chain

    path = _chain_path(args)
    as_json = getattr(args, "json", False)

    if not path.is_file():
        if as_json:
            print(json.dumps({"exists": False, "event_count": 0}))
        else:
            print("\n  No chain found. Run `organvm ledger genesis` to begin.\n")
        return 0

    result = verify_chain(path)

    if as_json:
        print(json.dumps({
            "exists": True,
            "valid": result.valid,
            "event_count": result.event_count,
            "last_sequence": result.last_sequence,
            "last_hash": result.last_hash,
            "errors": result.errors,
        }))
    else:
        status = "VALID" if result.valid else "CORRUPTED"
        print(f"\n  Testament Chain — {status}")
        print(f"  {'=' * 48}")
        print(f"  Events:        {result.event_count}")
        print(f"  Last sequence: {result.last_sequence}")
        if result.last_hash:
            print(f"  Last hash:     {result.last_hash[:30]}...")
        print(f"  Path:          {path}")
        if result.errors:
            print(f"\n  Errors ({len(result.errors)}):")
            for e in result.errors[:10]:
                print(f"    - {e}")
        print()

    return 0


def cmd_ledger_verify(args: argparse.Namespace) -> int:
    """Verify Testament Chain integrity."""
    from organvm_engine.ledger.chain import verify_chain

    path = _chain_path(args)
    if not path.is_file():
        print("  No chain found.")
        return 1

    result = verify_chain(path)

    if result.valid:
        print(
            f"\n  Chain VERIFIED — {result.event_count} events, "
            f"integrity intact from genesis to sequence {result.last_sequence}.\n",
        )
        return 0
    print(f"\n  Chain CORRUPTED — {len(result.errors)} error(s):")
    for e in result.errors:
        print(f"    - {e}")
    print()
    return 1


def cmd_ledger_log(args: argparse.Namespace) -> int:
    """Query the Testament Chain."""
    from organvm_engine.events.spine import EventSpine
    from organvm_engine.ledger.tiers import EventTier, classify_event_tier

    path = _chain_path(args)
    spine = EventSpine(path)

    event_type = getattr(args, "type", None)
    limit = getattr(args, "limit", 20)
    tier_filter = getattr(args, "tier", None)
    as_json = getattr(args, "json", False)

    records = spine.query(event_type=event_type, limit=limit)

    if tier_filter:
        target_tier = EventTier(tier_filter)
        records = [
            r for r in records if classify_event_tier(r.event_type) == target_tier
        ]

    if as_json:
        from dataclasses import asdict

        print(json.dumps([asdict(r) for r in records], indent=2, default=str))
    else:
        if not records:
            print("\n  No events found.\n")
            return 0

        print(f"\n  Testament Chain — {len(records)} events")
        print(f"  {'Seq':<6} {'Type':<28} {'Tier':<14} {'Timestamp':<20}")
        print(f"  {'-' * 70}")
        for r in records:
            tier = classify_event_tier(r.event_type).value
            ts = r.timestamp[:19] if r.timestamp else ""
            print(f"  {r.sequence:<6} {r.event_type:<28} {tier:<14} {ts}")
        print()

    return 0


def cmd_ledger_checkpoint(args: argparse.Namespace) -> int:
    """Create a Merkle checkpoint of events since last checkpoint."""
    from organvm_engine.events.spine import EventSpine
    from organvm_engine.ledger.merkle import compute_merkle_root

    path = _chain_path(args)
    dry_run = not getattr(args, "write", False)
    spine = EventSpine(path)

    # Find events since last checkpoint
    all_events = spine.query(limit=100_000)
    last_chk_seq = -1
    for ev in all_events:
        if ev.event_type == "testament.checkpoint":
            last_chk_seq = ev.sequence

    batch = [
        ev
        for ev in all_events
        if ev.sequence > last_chk_seq
        and ev.event_type != "testament.checkpoint"
    ]

    if not batch:
        print("  No events to checkpoint.")
        return 0

    leaves = [ev.hash for ev in batch if ev.hash]
    if not leaves:
        print("  No hashed events to checkpoint.")
        return 0

    root = compute_merkle_root(leaves)
    seq_range = (batch[0].sequence, batch[-1].sequence)

    if dry_run:
        print(
            f"\n  [dry-run] Would checkpoint {len(batch)} events "
            f"(seq {seq_range[0]}-{seq_range[1]})",
        )
        print(f"  Merkle root: {root}")
        print("\n  Run with --write to create checkpoint.\n")
        return 0

    record = spine.emit(
        event_type="testament.checkpoint",
        entity_uid="",
        source_organ="META-ORGANVM",
        source_repo="organvm-engine",
        actor="ledger:checkpoint",
        payload={
            "merkle_root": root,
            "event_range": list(seq_range),
            "event_count": len(batch),
            "prev_checkpoint_seq": last_chk_seq if last_chk_seq >= 0 else None,
        },
    )

    print(f"\n  Checkpoint created — sequence {record.sequence}")
    print(f"  Merkle root: {root}")
    print(f"  Events: {len(batch)} (seq {seq_range[0]}-{seq_range[1]})\n")
    return 0


def cmd_ledger_repair(args: argparse.Namespace) -> int:
    """Repair a corrupted chain by recomputing hashes and fixing sequences."""
    from organvm_engine.ledger.chain import repair_chain, verify_chain

    path = _chain_path(args)
    if not path.is_file():
        print("  No chain found.")
        return 1

    dry_run = not getattr(args, "write", False)

    # Check if repair is needed
    pre = verify_chain(path)
    if pre.valid:
        print(
            f"\n  Chain is already VALID ({pre.event_count} events). "
            "No repair needed.\n",
        )
        return 0

    if dry_run:
        print(
            f"\n  Chain has {len(pre.errors)} error(s) across "
            f"{pre.event_count} events.",
        )
        print("  Run with --write to repair.\n")
        return 0

    result = repair_chain(path)

    # Verify after repair
    post = verify_chain(path)

    print("\n  Chain Repair Complete")
    print(f"  {'=' * 48}")
    print(f"  Events read:    {result['events_read']}")
    print(f"  Events repaired: {result['events_repaired']}")
    if result.get("parse_errors"):
        print(f"  Parse errors:   {result['parse_errors']}")
    print(f"  Backup:         {result['backup']}")
    print(f"  Post-repair:    {'VALID' if post.valid else 'STILL CORRUPTED'}")
    print()

    return 0 if post.valid else 1

def cmd_ledger_anchor(args: argparse.Namespace) -> int:
    """Submit a Merkle checkpoint anchor to an external chain."""
    import os

    from web3 import Web3

    from organvm_engine.events.spine import EventSpine
    from organvm_engine.ledger.anchor import compute_anchor_hash

    path = _chain_path(args)
    spine = EventSpine(path)

    rpc_url = getattr(args, "rpc_url", None) or os.environ.get("BASE_RPC_URL")
    contract_addr = getattr(args, "contract", None) or os.environ.get("TESTAMENT_REGISTRY_ADDR")
    private_key = getattr(args, "private_key", None) or os.environ.get("ANCHOR_PRIVATE_KEY")

    if not all([rpc_url, contract_addr, private_key]):
        print("  Error: Missing connection parameters. Provide --rpc-url, --contract, and --private-key")
        print("         or set BASE_RPC_URL, TESTAMENT_REGISTRY_ADDR, and ANCHOR_PRIVATE_KEY env vars.")
        return 1

    dry_run = not getattr(args, "write", False)

    # Find the latest checkpoint
    all_events = spine.query(limit=100_000)
    checkpoint_ev = None
    for ev in reversed(all_events):
        if ev.event_type == "testament.checkpoint":
            checkpoint_ev = ev
            break

    if not checkpoint_ev:
        print("  No checkpoints found to anchor.")
        return 1

    payload = checkpoint_ev.payload
    merkle_root = payload.get("merkle_root")
    if not merkle_root:
        print("  Error: Checkpoint is missing merkle_root in payload.")
        return 1
    seq_range = payload.get("event_range", [0, 0])
    event_count = payload.get("event_count", 0)

    # We need the chain tip hash which is the hash of the last event in the checkpoint
    # Or for simplicity, use the checkpoint's own hash or the previous event's hash.
    # The requirement says: "The hash of the last event in the anchored range."
    chain_tip_hash = ""
    for ev in reversed(all_events):
        if ev.sequence == seq_range[1] and ev.hash is not None:
            chain_tip_hash = ev.hash
            break

    if not chain_tip_hash:
        print("  Could not find chain tip hash for checkpoint range.")
        return 1

    import datetime
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    anchor_hash = compute_anchor_hash(
        merkle_root=str(merkle_root),
        chain_tip_hash=chain_tip_hash,
        sequence_start=int(seq_range[0]),
        sequence_end=int(seq_range[1]),
        event_count=int(event_count),
        timestamp=timestamp,
    )

    if dry_run:
        print(f"\n  [dry-run] Would anchor checkpoint (seq {seq_range[0]}-{seq_range[1]})")
        print(f"  Merkle root:    {merkle_root}")
        print(f"  Chain tip hash: {chain_tip_hash}")
        print(f"  Anchor hash:    {anchor_hash}")
        print("\n  Run with --write to submit to chain.\n")
        return 0

    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            print("  Error: Could not connect to RPC node.")
            return 1

        account = w3.eth.account.from_key(private_key)

        # Simplified ABI for the registerAnchor function
        abi = [{
            "inputs": [
                {"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
                {"internalType": "bytes32", "name": "chainTipHash", "type": "bytes32"},
                {"internalType": "uint256", "name": "sequenceStart", "type": "uint256"},
                {"internalType": "uint256", "name": "sequenceEnd", "type": "uint256"},
                {"internalType": "uint256", "name": "eventCount", "type": "uint256"},
                {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
                {"internalType": "bytes32", "name": "anchorHash", "type": "bytes32"},
            ],
            "name": "registerAnchor",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        }]

        contract = w3.eth.contract(address=w3.to_checksum_address(str(contract_addr)), abi=abi)

        # Convert hex strings to bytes32 where needed
        # We assume hashes are strings starting with "sha256:" and 64 hex chars,
        # but Solidity bytes32 requires 32 bytes (64 hex chars).
        def to_bytes32(h: str) -> bytes:
            if h.startswith("sha256:"):
                h = h[7:]
            return bytes.fromhex(h)

        # Parse timestamp into a unix epoch uint256
        dt = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=datetime.timezone.utc)
        ts_uint = int(dt.timestamp())

        # Build EIP-1559 transaction
        base_fee = w3.eth.get_block('latest').get('baseFeePerGas', 0)
        max_priority_fee = w3.eth.max_priority_fee

        if base_fee is None:
            base_fee = 0

        max_fee_per_gas = base_fee * 2 + max_priority_fee

        from typing import cast

        from web3.types import TxParams

        tx_params = cast(TxParams, {
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address),
            'gas': 2000000,
            'maxFeePerGas': max_fee_per_gas,
            'maxPriorityFeePerGas': max_priority_fee,
        })

        tx = contract.functions.registerAnchor(
            to_bytes32(str(merkle_root)),
            to_bytes32(chain_tip_hash),
            int(seq_range[0]),
            int(seq_range[1]),
            int(event_count),
            ts_uint,
            to_bytes32(anchor_hash),
        ).build_transaction(tx_params)

        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.get("status") == 1:
            print("\n  Anchor submitted successfully!")
            print(f"  Transaction hash: {tx_hash.hex()}")
            print(f"  Anchor hash:      {anchor_hash}")
            return 0
        print("\n  Anchor submission failed! Transaction reverted.")
        return 1

    except Exception as e:
        print(f"\n  Error during anchoring: {e}")
        return 1

