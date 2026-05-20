"""Poll log/experiment_state.json and emit one event per state change.

Usage:
    python -u project/monitor_state.py [interval_seconds]

Exits with code 0 when status becomes 'done', 2 on error.
"""
import json
import sys
import time
from pathlib import Path

STATE = Path("D:/YJ-Agent/log/experiment_state.json")


def main():
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    prev = None
    while True:
        try:
            d = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"state-read-err: {ex}", flush=True)
            time.sleep(interval)
            continue
        p = d.get("progress", {}) or {}
        e = d.get("error", {}) or {}
        status = d.get("status")
        ep = p.get("current_epoch")
        total = p.get("total_epochs")
        loss = p.get("last_loss")
        val = p.get("last_val_metric")
        err_type = e.get("type")
        cur = (status, ep, loss, val, err_type)
        if cur != prev:
            print(
                f"[ep {ep}/{total}] status={status} loss={loss} val_auc={val}",
                flush=True,
            )
            prev = cur
        if err_type:
            print(f"ERROR: {err_type}: {e.get('message')}", flush=True)
            sys.exit(2)
        if status in ("done", "failed", "stopped"):
            print(f"TRAINING {status.upper()}", flush=True)
            sys.exit(0)
        time.sleep(interval)


if __name__ == "__main__":
    main()
