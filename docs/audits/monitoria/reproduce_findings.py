"""Compatibility entry point: the audit probes are now acceptance regressions.
Run: .venv/bin/python -m pytest docs/audits/monitoria/reproduce_findings.py -q
PASS now means the corrected behavior was verified, rather than a defect reproduced.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from test_monitoria_regressions import *  # noqa: F401,F403
