#!/usr/bin/env python3
"""
scripts/analyze_prod_logs.py

Analyzes GalleryVault production logs (backend, frontend, db),
extracts ERROR / WARNING messages, calculates HTTP status code
distributions, top routes, and exception categories, then prints
a formatted summary report.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Terminal colors for pretty reporting
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_CYAN = "\033[36m"
COLOR_MAGENTA = "\033[35m"
COLOR_DIM = "\033[2m"


@dataclass
class LogEntry:
    source: str
    level: str
    timestamp: str
    message: str
    exception_type: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HttpRecord:
    source: str
    method: str
    path: str
    status_code: int


class LogAnalyzer:
    def __init__(self, use_color: bool = True):
        self.use_color = use_color and sys.stdout.isatty()
        self.total_lines = 0
        self.files_analyzed: List[str] = []

        self.errors: List[LogEntry] = []
        self.warnings: List[LogEntry] = []
        self.http_records: List[HttpRecord] = []

        self.exception_counts: Counter[str] = Counter()
        self.status_code_counts: Counter[int] = Counter()
        self.route_counts: Counter[str] = Counter()
        self.route_errors: Counter[str] = Counter()

        self.component_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"lines": 0, "errors": 0, "warnings": 0, "http_reqs": 0}
        )

    def _c(self, text: str, color: str) -> str:
        if not self.use_color:
            return text
        return f"{color}{text}{COLOR_RESET}"

    # Regex patterns
    RE_NGINX_ACCESS = re.compile(
        r'^(?P<ip>\S+)\s+-\s+\S*\s+\[(?P<time>[^\]]+)\]\s+"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+[^"]+"\s+(?P<status>\d{3})\s+(?P<bytes>\d+)'
    )
    RE_NGINX_ERROR = re.compile(
        r'^(?P<time>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[(?P<level>[a-z]+)\]\s+(?P<pid>\d+)#(?P<tid>\d+):\s+(?P<msg>.*)$'
    )
    RE_UVICORN_ACCESS = re.compile(
        r'(?:INFO:\s+)?(?P<ip>\S+:\d+)\s+-\s+"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/[0-9.]+"\s+(?P<status>\d{3})'
    )
    RE_STANDARD_LOG = re.compile(
        r'^(?P<time>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[^\s]*)\s+(?P<level>[A-Z]+)\s+(?P<logger>[^:]+):\s+(?P<msg>.*)$'
    )
    RE_POSTGRES_LOG = re.compile(
        r'^(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[^\s]*)\s*(?:[A-Z]{3,4}\s*)?(?:\[\d+\]\s*)?(?P<level>LOG|ERROR|FATAL|PANIC|WARNING|NOTICE|DETAIL|HINT):\s+(?P<msg>.*)$'
    )
    RE_EXCEPTION_NAME = re.compile(r'\b([A-Z][a-zA-Z0-9]*(?:Error|Exception|Fault|Interrupt|Exit))\b')

    def analyze_file(self, file_path: Path) -> None:
        name = file_path.name.lower()
        if "backend" in name:
            component = "backend"
        elif "frontend" in name or "nginx" in name:
            component = "frontend"
        elif "db" in name or "postgres" in name:
            component = "db"
        else:
            component = "other"

        self.files_analyzed.append(str(file_path))

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    self.total_lines += 1
                    self.component_stats[component]["lines"] += 1
                    self._parse_line(component, line.rstrip("\r\n"))
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)

    def _parse_line(self, component: str, line: str) -> None:
        if not line.strip():
            return

        # 1. Try parsing structured JSON
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                level = str(data.get("level", "INFO")).upper()
                msg = str(data.get("message", ""))
                time_str = str(data.get("time", ""))
                exc_type = data.get("exception_type")
                if not exc_type and data.get("exception"):
                    m_exc = self.RE_EXCEPTION_NAME.search(str(data["exception"]))
                    if m_exc:
                        exc_type = m_exc.group(1)

                entry = LogEntry(
                    source=component,
                    level=level,
                    timestamp=time_str,
                    message=msg,
                    exception_type=exc_type,
                    extra=data,
                )

                if level in ("ERROR", "CRITICAL", "FATAL"):
                    self.errors.append(entry)
                    self.component_stats[component]["errors"] += 1
                    if exc_type:
                        self.exception_counts[exc_type] += 1
                    else:
                        self._extract_generic_exception(msg)
                elif level in ("WARN", "WARNING"):
                    self.warnings.append(entry)
                    self.component_stats[component]["warnings"] += 1

                # Check if it's an HTTP access log record in JSON
                if "status_code" in data and "path" in data:
                    st = int(data["status_code"])
                    method = str(data.get("method", "GET"))
                    path = str(data["path"])
                    self._record_http(component, method, path, st)
                return
            except json.JSONDecodeError:
                pass

        # 2. Check Nginx Access Log
        m_ng = self.RE_NGINX_ACCESS.search(line)
        if m_ng:
            st = int(m_ng.group("status"))
            method = m_ng.group("method")
            path = m_ng.group("path").split("?")[0]
            self._record_http(component, method, path, st)
            return

        # 3. Check Uvicorn Access Log
        m_uvi = self.RE_UVICORN_ACCESS.search(line)
        if m_uvi:
            st = int(m_uvi.group("status"))
            method = m_uvi.group("method")
            path = m_uvi.group("path").split("?")[0]
            self._record_http(component, method, path, st)
            return

        # 4. Check Nginx Error Log
        m_ng_err = self.RE_NGINX_ERROR.search(line)
        if m_ng_err:
            lvl = m_ng_err.group("level").upper()
            msg = m_ng_err.group("msg")
            time_str = m_ng_err.group("time")
            if lvl in ("ERROR", "CRIT", "ALERT", "EMERG"):
                self.component_stats[component]["errors"] += 1
                self.errors.append(LogEntry(source=component, level="ERROR", timestamp=time_str, message=msg))
                self.exception_counts[f"Nginx:{lvl}"] += 1
            elif lvl in ("WARN", "WARNING"):
                self.component_stats[component]["warnings"] += 1
                self.warnings.append(LogEntry(source=component, level="WARNING", timestamp=time_str, message=msg))
            return

        # 5. Check Postgres Log
        m_pg = self.RE_POSTGRES_LOG.search(line)
        if m_pg:
            lvl = m_pg.group("level").upper()
            msg = m_pg.group("msg")
            time_str = m_pg.group("time")
            if lvl in ("ERROR", "FATAL", "PANIC"):
                self.component_stats[component]["errors"] += 1
                self.errors.append(LogEntry(source=component, level=lvl, timestamp=time_str, message=msg))
                self.exception_counts[f"Postgres:{lvl}"] += 1
            elif lvl in ("WARNING",):
                self.component_stats[component]["warnings"] += 1
                self.warnings.append(LogEntry(source=component, level=lvl, timestamp=time_str, message=msg))
            return

        # 6. Check Standard Python / Formatted Log
        m_std = self.RE_STANDARD_LOG.search(line)
        if m_std:
            lvl = m_std.group("level").upper()
            msg = m_std.group("msg")
            time_str = m_std.group("time")
            exc_match = self.RE_EXCEPTION_NAME.search(msg)
            exc_type = exc_match.group(1) if exc_match else None

            entry = LogEntry(source=component, level=lvl, timestamp=time_str, message=msg, exception_type=exc_type)
            if lvl in ("ERROR", "CRITICAL", "FATAL"):
                self.component_stats[component]["errors"] += 1
                self.errors.append(entry)
                if exc_type:
                    self.exception_counts[exc_type] += 1
                else:
                    self._extract_generic_exception(msg)
            elif lvl in ("WARN", "WARNING"):
                self.component_stats[component]["warnings"] += 1
                self.warnings.append(entry)
            return

        # 7. Fallback keywords scan for raw lines
        upper_line = line.upper()
        if "ERROR" in upper_line or "CRITICAL" in upper_line or "FATAL" in upper_line:
            self.component_stats[component]["errors"] += 1
            exc_match = self.RE_EXCEPTION_NAME.search(line)
            exc_type = exc_match.group(1) if exc_match else None
            self.errors.append(LogEntry(source=component, level="ERROR", timestamp="", message=line, exception_type=exc_type))
            if exc_type:
                self.exception_counts[exc_type] += 1
            else:
                self._extract_generic_exception(line)
        elif "WARN" in upper_line:
            self.component_stats[component]["warnings"] += 1
            self.warnings.append(LogEntry(source=component, level="WARNING", timestamp="", message=line))

    def _extract_generic_exception(self, msg: str) -> None:
        exc_match = self.RE_EXCEPTION_NAME.search(msg)
        if exc_match:
            self.exception_counts[exc_match.group(1)] += 1
        else:
            self.exception_counts["UnclassifiedError"] += 1

    def _record_http(self, component: str, method: str, path: str, status_code: int) -> None:
        self.http_records.append(HttpRecord(source=component, method=method, path=path, status_code=status_code))
        self.component_stats[component]["http_reqs"] += 1
        self.status_code_counts[status_code] += 1
        route_key = f"{method} {path}"
        self.route_counts[route_key] += 1
        if status_code >= 400:
            self.route_errors[route_key] += 1

    def print_report(self) -> None:
        sep = "=" * 70
        sub_sep = "-" * 70

        print()
        print(self._c(sep, COLOR_CYAN))
        print(self._c("         GALLERYVAULT PRODUCTION LOG ANALYSIS REPORT", COLOR_BOLD + COLOR_CYAN))
        print(self._c(sep, COLOR_CYAN))
        print(f"Generated at:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Files Processed:  {len(self.files_analyzed)}")
        for f in self.files_analyzed:
            print(f"  - {f}")
        print(f"Total Log Lines:  {self.total_lines:,}")
        print(self._c(sub_sep, COLOR_DIM))

        # 1. Component Overview
        print(self._c("1. COMPONENT OVERVIEW", COLOR_BOLD))
        print(f"  {'Component':<12} | {'Lines':<10} | {'Errors':<8} | {'Warnings':<10} | {'HTTP Reqs':<10}")
        print(f"  {'-'*12}-+-{'-'*10}-+-{'-'*8}-+-{'-'*10}-+-{'-'*10}")
        for comp in ["backend", "frontend", "db", "other"]:
            if comp in self.component_stats or comp in ("backend", "frontend", "db"):
                stats = self.component_stats[comp]
                err_str = self._c(f"{stats['errors']:<8}", COLOR_RED if stats['errors'] > 0 else COLOR_GREEN)
                warn_str = self._c(f"{stats['warnings']:<10}", COLOR_YELLOW if stats['warnings'] > 0 else COLOR_GREEN)
                print(f"  {comp:<12} | {stats['lines']:<10,} | {err_str} | {warn_str} | {stats['http_reqs']:<10,}")
        print()

        # 2. HTTP Status Codes Distribution
        print(self._c("2. HTTP STATUS CODE DISTRIBUTION", COLOR_BOLD))
        if not self.status_code_counts:
            print("  No HTTP access records found in logs.")
        else:
            total_reqs = sum(self.status_code_counts.values())
            # Group by 2xx, 3xx, 4xx, 5xx
            categories = defaultdict(int)
            for code, count in self.status_code_counts.items():
                cat = f"{code // 100}xx"
                categories[cat] += count

            print(f"  Total Requests: {total_reqs:,}")
            for cat in sorted(categories.keys()):
                cnt = categories[cat]
                pct = (cnt / total_reqs * 100) if total_reqs else 0
                color = COLOR_GREEN if cat.startswith("2") else (COLOR_YELLOW if cat.startswith(("3", "4")) else COLOR_RED)
                bar = "■" * int(pct / 5)
                print(f"    {self._c(cat, color)}: {cnt:>6,} ({pct:>5.1f}%) {self._c(bar, color)}")

            print("\n  Detailed Status Codes:")
            for code in sorted(self.status_code_counts.keys()):
                cnt = self.status_code_counts[code]
                pct = (cnt / total_reqs * 100) if total_reqs else 0
                c = COLOR_GREEN if code < 400 else (COLOR_YELLOW if code < 500 else COLOR_RED)
                print(f"    {self._c(str(code), c)}: {cnt:>6,} ({pct:>5.1f}%)")
        print()

        # 3. Top HTTP Routes
        print(self._c("3. TOP HTTP ROUTES (REQUESTS & ERRORS)", COLOR_BOLD))
        if not self.route_counts:
            print("  No HTTP route traffic recorded.")
        else:
            print(f"  {'Method & Path':<45} | {'Reqs':<8} | {'Errors (≥400)':<12}")
            print(f"  {'-'*45}-+-{'-'*8}-+-{'-'*12}")
            for route, count in self.route_counts.most_common(12):
                err_cnt = self.route_errors.get(route, 0)
                err_display = self._c(f"{err_cnt:<12}", COLOR_RED if err_cnt > 0 else COLOR_GREEN)
                print(f"  {route[:45]:<45} | {count:<8,} | {err_display}")
        print()

        # 4. Exception & Error Type Breakdown
        print(self._c("4. EXCEPTION & ERROR DISTRIBUTION", COLOR_BOLD))
        if not self.exception_counts:
            print(self._c("  No exceptions or error signatures detected! [HEALTHY]", COLOR_GREEN))
        else:
            for exc, count in self.exception_counts.most_common(10):
                print(f"  - {self._c(exc, COLOR_RED)}: {count} occurrence(s)")
        print()

        # 5. Recent Error Samples
        print(self._c("5. RECENT / SAMPLE ERROR MESSAGES", COLOR_BOLD))
        if not self.errors:
            print(self._c("  No error messages found. All services healthy during collection period.", COLOR_GREEN))
        else:
            sample_errors = self.errors[:10]
            for idx, err in enumerate(sample_errors, start=1):
                ts = f"[{err.timestamp}] " if err.timestamp else ""
                src = f"({err.source.upper()})"
                header = f"  [{idx}] {src} {ts}{err.level}:"
                print(self._c(header, COLOR_RED))
                # Truncate long message
                msg_lines = err.message.strip().split("\n")
                first_line = msg_lines[0][:120]
                print(f"      {first_line}")
                if len(msg_lines) > 1:
                    print(f"      ... (+{len(msg_lines)-1} traceback lines)")
            if len(self.errors) > 10:
                print(self._c(f"\n  ... and {len(self.errors) - 10} more error(s).", COLOR_DIM))
        print()
        print(self._c(sep, COLOR_CYAN))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze GalleryVault production log dump.")
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Path to directory containing logs or a single log file (defaults to most recent /tmp/galleryvault-prod-logs*)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable terminal ANSI colors")
    args = parser.parse_args()

    target_path: Optional[Path] = None
    if args.target:
        target_path = Path(args.target).resolve()
    else:
        # Look for the latest /tmp/galleryvault-prod-logs*
        candidates = sorted(glob.glob("/tmp/galleryvault-prod-logs*"), key=os.path.getmtime, reverse=True)
        if candidates:
            target_path = Path(candidates[0]).resolve()

    if not target_path or not target_path.exists():
        print(f"Error: Target path '{args.target or '/tmp/galleryvault-prod-logs*'}' does not exist.", file=sys.stderr)
        return 1

    analyzer = LogAnalyzer(use_color=not args.no_color)

    if target_path.is_file():
        analyzer.analyze_file(target_path)
    elif target_path.is_dir():
        log_files = sorted(target_path.glob("**/*.log"))
        if not log_files:
            # Check if there are any regular files
            log_files = [p for p in sorted(target_path.iterdir()) if p.is_file() and not p.name.endswith(".tar.gz")]
        for p in log_files:
            analyzer.analyze_file(p)

    analyzer.print_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
