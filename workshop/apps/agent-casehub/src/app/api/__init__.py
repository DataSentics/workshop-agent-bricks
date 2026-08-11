"""
HTTP routes.

The routes the UI calls sit under the API prefix. The probes, the UI itself and the
agent routes stay at the root, where the platform and the supervisor reach them without
knowing how the API is namespaced.
"""
