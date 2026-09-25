"""XAUPY Python Engine.

Task 007 adds the deterministic Direction -> Pullback -> Trigger strategy state
machine and exposes read-only strategy state over IPC. Trading execution remains
hard-locked; no trade intent or broker action is introduced by this task.
"""

__version__ = "0.7.0-task007"
