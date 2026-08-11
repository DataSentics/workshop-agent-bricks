"""
A mocked Outlook mailbox, served as a Databricks App.

The same mailbox is reachable two ways: an Outlook-like web UI on top of the REST API,
and an MCP server an agent connects to. That is the point of the demo — a person and an
agent working in one inbox — so the two surfaces are deliberately thin wrappers over a
single store rather than separate implementations.

Nothing here talks to Microsoft. Each user is seeded from a committed JSON file and kept
in a Unity Catalog volume.
"""
