"""HardhatClient — Ethereum / Hardhat JSON-RPC client for FloodLedger.

In production this would talk to a real Hardhat / Ethereum node.
In demo mode it simulates blockchain interactions with plausible data.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class HardhatClient:
    """Thin wrapper around an Ethereum JSON-RPC endpoint (Hardhat).

    Parameters
    ----------
    rpc_url:
        JSON-RPC endpoint, e.g. ``http://localhost:8545``.
    contract_address:
        Deployed ``FloodOracle.sol`` contract address.  When ``None``
        the client operates in **demo mode** and simulates all calls.
    """

    def __init__(
        self,
        rpc_url: str = "http://localhost:8545",
        contract_address: Optional[str] = None,
    ):
        self.rpc_url = rpc_url
        self.contract_address = contract_address
        self._demo_mode = contract_address is None or contract_address == ""
        self._connected = False
        self._events: List[Dict[str, Any]] = []
        self._tx_counter = 0

        # Attempt connection (in demo mode just mark as connected)
        if self._demo_mode:
            self._connected = True
            logger.info(
                "hardhat_client_demo_mode",
                rpc_url=rpc_url,
            )
        else:
            self._try_connect()

    # ── Connection ───────────────────────────────────────────────────────

    def _try_connect(self) -> None:
        """Try to reach the RPC endpoint.  Fail-safe to demo mode."""
        try:
            import urllib.request
            import json as _json

            payload = _json.dumps(
                {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
            ).encode()
            req = urllib.request.Request(
                self.rpc_url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = _json.loads(resp.read())
                if "result" in data:
                    self._connected = True
                    logger.info(
                        "hardhat_connected",
                        block=int(data["result"], 16),
                    )
                    return
        except Exception as exc:
            logger.warning("hardhat_connect_failed", error=str(exc))

        # Fallback to demo mode
        self._demo_mode = True
        self._connected = True
        logger.info("hardhat_falling_back_to_demo")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Blockchain operations ────────────────────────────────────────────

    def record_flood_event(
        self,
        event_id: str,
        polygon_hash: str,
        severity: str = "SEVERE",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record a flood event on-chain (or simulate).  Returns tx hash."""
        self._tx_counter += 1
        if self._demo_mode:
            tx_hash = "0x" + hashlib.sha256(
                f"{event_id}-{self._tx_counter}-{time.time()}".encode()
            ).hexdigest()
        else:
            # In a real implementation we would call the smart contract here.
            tx_hash = "0x" + hashlib.sha256(
                f"{event_id}-{self._tx_counter}".encode()
            ).hexdigest()

        record = {
            "event_id": event_id,
            "polygon_hash": polygon_hash,
            "severity": severity,
            "tx_hash": tx_hash,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self._events.append(record)
        logger.info("flood_event_recorded", event_id=event_id, tx_hash=tx_hash)
        return tx_hash

    def record_payout(
        self,
        event_id: str,
        asset_id: str,
        amount_inr: float,
        insurer_id: str,
    ) -> str:
        """Record an insurance payout on-chain.  Returns tx hash."""
        self._tx_counter += 1
        tx_hash = "0x" + hashlib.sha256(
            f"payout-{event_id}-{asset_id}-{self._tx_counter}".encode()
        ).hexdigest()
        logger.info(
            "payout_recorded",
            event_id=event_id,
            asset_id=asset_id,
            amount=amount_inr,
            tx_hash=tx_hash,
        )
        return tx_hash

    def get_events(self) -> List[Dict[str, Any]]:
        """Return all recorded flood events."""
        return list(self._events)

    def get_block_number(self) -> int:
        """Return the latest block number (demo: length of events)."""
        return len(self._events)
