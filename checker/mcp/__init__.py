"""The Themis MCP surface — how an orchestrator reaches the engine.

Integration plan §22: *"the first MCP server should actually be Themis itself"*.

Ring 2. Every tool is read-only, every call is policy-decided (`policy.py`), and
every refusal the engine produces reaches the caller verbatim. No tool returns a
legal conclusion, because no tool has one to return.
"""
