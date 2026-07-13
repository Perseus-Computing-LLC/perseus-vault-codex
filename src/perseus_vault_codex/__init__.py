"""Perseus Vault Codex — persistent, encrypted, local-first memory for Codex.

Wraps the Perseus Vault binary as a minimal 5-tool MCP server so any Codex
session gains cross-session memory: ``perseus_remember``, ``perseus_recall``,
``perseus_forget``, ``perseus_reflect``, ``perseus_status``.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
