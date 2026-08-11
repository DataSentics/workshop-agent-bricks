"""
The agent-facing surface: the mailbox exposed as MCP tools.

It is a thin wrapper over the same store the REST API uses, so a person clicking around
the UI and an agent calling tools are working in one mailbox rather than in two copies
of one. Nothing in here holds state of its own.
"""
