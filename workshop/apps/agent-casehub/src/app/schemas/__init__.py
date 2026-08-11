"""
The models the HTTP surface exchanges.

The store speaks dicts, because that is what a SQL result set is and what the agent
hands to the model as a tool result. These models are the boundary: they say what the
UI is promised, and FastAPI validates the dicts against them on the way out.
"""
