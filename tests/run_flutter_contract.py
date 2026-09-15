"""Starts an isolated local API and runs the real Flutter HTTP contract test."""
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import socket
import sys

import uvicorn


def main():
    flutter = shutil.which("flutter")
    if not flutter:
        raise RuntimeError("Flutter SDK não encontrado no PATH")
    sdk = Path(flutter).parent
    dart = sdk / "cache" / "dart-sdk" / "bin" / ("dart.exe" if os.name == "nt" else "dart")
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "Lumen-backend"))
    with tempfile.TemporaryDirectory() as temp:
        os.environ.update(DATABASE_URL=f"sqlite:///{Path(temp) / 'contract.db'}", DEBUG="false",
            PAYMENT_PROVIDER="sandbox", PAYMENT_WEBHOOK_SECRET="contract-only-secret",
            SHIPPING_FLAT_RATE_CENTS="1500", AUTO_CREATE_TABLES="true", SEED_CATALOG="true")
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config("app.main:app", log_level="warning"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if time.monotonic() > deadline:
                    raise RuntimeError("API não iniciou")
                time.sleep(.05)
            result = subprocess.run([str(dart), str(sdk / "cache" / "flutter_tools.snapshot"),
                "test", "test/backend_contract_test.dart", f"--dart-define=CONTRACT_API=http://127.0.0.1:{port}/api/v1"],
                cwd=root / "lumen-flutter", timeout=120)
            return result.returncode
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()
            from app.core.database import engine
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
