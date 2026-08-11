"""
Configuration and caller identity, the cross-cutting concerns every other layer reads.

Intended to sit at the bottom of the dependency graph, depending on nothing around it,
so that anything may reach in here and nothing here has to reach back out.
"""
