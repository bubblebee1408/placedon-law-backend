"""The agent runtime: typed plans, persisted steps, bounded correction.

Ring 3 (INFERENCE). It may read from the rings below it; **nothing here may reach a Ring 0
legal decision**. A run produces PROPOSALS and a trace; whether a proposal is legally correct
is decided by the deterministic core, never here.
"""
