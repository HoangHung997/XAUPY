"""Isolated MT5 reader jobs. Blocking terminal synchronization never runs on IPC."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import uuid


class HistoryJobs:
    def __init__(self, root: Path) -> None:
        self.root = root / "market-history"
        self.process: subprocess.Popen | None = None
        self.job_dir: Path | None = None
        self.output: Any = None

    def start(self, terminal: str, symbol: str, *, model='M1_OHLC', from_date='', to_date='', context=None) -> dict:
        if self.process is not None and self.process.poll() is None:
            raise ValueError("A history download is already running")
        path = Path(terminal)
        if not path.is_absolute() or not path.is_file() or path.name.lower() != "terminal64.exe":
            raise ValueError("Choose the installed MT5 terminal64.exe")
        if not symbol or len(symbol) > 80 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in symbol):
            raise ValueError("Invalid symbol")
        if model not in ('M1_OHLC','REAL_TICKS'):raise ValueError('Unknown history model')
        if model=='REAL_TICKS':
            from .tick_collect import parse_range
            parse_range(from_date,to_date)
        self.job_dir = self.root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        self.job_dir.mkdir(parents=True)
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command += ["-m", "xaupy_engine.main"]
        command += ["--collect-ticks" if model=='REAL_TICKS' else "--collect-history", "--terminal", str(path), "--symbol", symbol, "--output", str(self.job_dir)]
        if model=='REAL_TICKS':
            context_path=self.job_dir/'tick-context.json'
            context_path.write_text(json.dumps(context or {},ensure_ascii=False),encoding='utf-8')
            command += ['--from-date',from_date,'--to-date',to_date,'--context-file',str(context_path)]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        # A frozen onefile child must not share its parent's temporary extraction.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        if self.output is not None:
            self.output.close()
        self.output = (self.job_dir / "collector.log").open("wb")
        try:
            self.process = subprocess.Popen(command, stdout=self.output, stderr=subprocess.STDOUT, env=env,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            self.output.close()
            self.output = None
            raise
        return self.status()

    def status(self) -> dict:
        if self.job_dir is None:
            return {"status": "IDLE", "root": str(self.root), "broker_execution_requested": False}
        report = {}
        progress = self.job_dir / "progress.json"
        if progress.exists():
            try:
                report = json.loads(progress.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        code = self.process.poll() if self.process is not None else None
        if code is not None and self.output is not None:
            self.output.close()
            self.output = None
        status = "RUNNING" if code is None else report.get("status", "FAILED") if code == 0 else "FAILED"
        return {**report, "status": status, "output_directory": str(self.job_dir), "exit_code": code,
                "log_path": str(self.job_dir / "collector.log"), "broker_execution_requested": False}

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if os.name == "nt":
                # The owned PyInstaller bootloader can have a reader child process.
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=3, check=False)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.output is not None:
            self.output.close()
            self.output = None
