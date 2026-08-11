"""
The CaseHub agent.

This is the piece that makes CaseHub an agent rather than another MCP server. An MCP
server hands the caller a list of tools and lets the caller decide what to do with them;
the supervisor stays in charge and has to know that closing a case needs a resolution.
An agent owns its own subject. The supervisor says "close Alpine's payroll case, the
bank details are fixed now", and CaseHub works out which case that is, notices it has no
resolution text, writes one, and closes it.

The distinction is the point of this part of the workshop, and it is easiest to see by
watching where the decisions get made.

Implemented as an MLflow ResponsesAgent because that is what a Databricks App has to
expose for the Agent Bricks Supervisor to accept it as a custom agent. The wire format
is the OpenAI Responses schema: `input` in, `output` out.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import TYPE_CHECKING, Any

from databricks.sdk import WorkspaceClient
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

from app.agent.tools import TOOLS, call_tool
from app.core.identity import current_caller
from app.store.cases import ENGINEERS, SEVERITIES, STATUSES

if TYPE_CHECKING:
    from collections.abc import Generator

    from app.core.settings import AgentSettings
    from app.store.cases import CaseStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""\
You are CaseHub, the support case desk for Saldo, a cloud accounting platform used by companies
in the Czech Republic and Slovakia. You work the queue: you look cases up, you keep them
accurate, and you close them when they are done.

You are being called by another agent, not by a person typing in a chat window. So:

- Do the work rather than describing it. If you have been asked to reassign a case, reassign it.
- If you genuinely cannot tell which case is meant, list the candidates and stop. Do not guess
  between two cases and act on one of them.
- Answer with what you did and what the case looks like now. Be brief. No preamble.

Things about this queue that you are expected to know:

- Severity runs {", ".join(SEVERITIES)}, S1 being the worst. Status is one of
  {", ".join(STATUSES)}.
- "Open cases" almost always means everything that is not closed. Pass open_only for that.
  There is also a status literally called Open, which means nobody has picked the case up yet -
  only filter on it when somebody clearly means that narrower thing. Getting this backwards
  hides every case currently being worked on, so when in doubt use open_only.
- Cases are assigned to one of: {", ".join(ENGINEERS)}.
- Closing a case takes a resolution - what was actually done. Do not close one without it. If
  you were told to close a case and were given the reason in passing, that reason is the
  resolution; write it down properly rather than asking for it again.
- A case can be linked to the incident or the payroll run it is about. Do that when you learn
  the connection, because it is what makes the case findable later.
- Notes are permanent and get read months afterwards by somebody with no memory of any of this.
  Write them for that person.

What you do not do: you have no view of platform availability, deployments, contracts or what a
customer is billed. If you are asked about those, say so plainly and answer the part about cases.
"""


def _to_chat_messages(request: ResponsesAgentRequest) -> list[dict[str, Any]]:
    """
    Convert Responses-shaped input into chat-completions-shaped messages.

    The supervisor speaks the Responses schema; the Foundation Model endpoint speaks
    chat completions. This is the join between them, and it only has to handle what
    actually arrives: plain text turns.

    Args:
        request: What the supervisor sent.

    Returns:
        The messages to open the tool loop with, the system prompt first.
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in request.input:
        data = item if isinstance(item, dict) else item.model_dump(exclude_none=True)
        role = data.get("role")
        if role not in ("user", "assistant", "system"):
            continue
        content = data.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
                and part.get("type") in ("input_text", "output_text", "text")
            )
        if content:
            # A system turn from the caller is folded into the conversation rather than
            # kept as one: CaseHub's own instructions are the system prompt, and a
            # second one would be read as competing with it.
            messages.append(
                {"role": "user" if role == "system" else role, "content": content},
            )
    return messages


class CaseHubAgent(ResponsesAgent):
    """
    Reads the request, runs a tool-calling loop, reports what it did.
    """

    def __init__(self, store: CaseStore, settings: AgentSettings) -> None:
        self._store = store
        self._settings = settings
        self._client: Any = None
        self._client_guard = threading.Lock()

    @property
    def client(self) -> Any:
        """
        The OpenAI-compatible client for the Foundation Model endpoint.

        Built on first use, so an application whose serving endpoints are unreachable
        still starts and reports the failure on the request that needed them.

        One agent object serves everybody, on several worker threads at once, so the
        first build is guarded: constructing this reaches the workspace to resolve the
        endpoint, and without the lock the first few requests would each pay for that.
        """
        if self._client is None:
            with self._client_guard:
                if self._client is None:
                    self._client = (
                        WorkspaceClient().serving_endpoints.get_open_ai_client()
                    )
        return self._client

    def _stream(
        self,
        request: ResponsesAgentRequest,
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Work the request, emitting each output item as it is produced.

        This is the whole agent. predict and predict_stream both read from it, so the
        two cannot drift: MLflow's canonical shape is that predict is predict_stream
        with the items collected, and an implementation that runs the loop twice
        returns a different transcript on /invocations than on /responses.

        Every item goes out as response.output_item.done, which is the only event type
        the canonical tool-calling example uses. Emitting them as the loop runs rather
        than at the end is also what keeps the connection alive: MLflow's AgentServer
        flushes one SSE frame per yielded event, so the first tool call reaches the
        caller within a few seconds instead of after the whole loop.

        Args:
            request: What the supervisor sent.

        Yields:
            A function_call and function_call_output item per tool used, then the
            assistant message.
        """
        # Bound by the identity middleware from the forwarded headers, so the agent
        # works the same desk the person calling it sees in the UI.
        caller = current_caller()
        messages = _to_chat_messages(request)
        used = 0

        for _turn in range(self._settings.max_turns):
            completion = self.client.chat.completions.create(
                model=self._settings.llm_endpoint,
                messages=messages,
                tools=list(TOOLS),
                max_tokens=self._settings.max_tokens,
            )
            choice = completion.choices[0].message
            calls = choice.tool_calls or []

            if not calls:
                yield from self._answer((choice.content or "").strip())
                logger.info("answered after %d tool call(s)", used)
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in calls
                    ],
                },
            )

            for call in calls:
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=self.create_function_call_item(
                        id=str(uuid.uuid4()),
                        call_id=call.id,
                        name=call.function.name,
                        arguments=call.function.arguments or "{}",
                    ),
                )
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                result = call_tool(self._store, caller, call.function.name, arguments)
                used += 1
                logger.info("tool %s(%s)", call.function.name, arguments)
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=self.create_function_call_output_item(
                        call_id=call.id,
                        output=result,
                    ),
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result},
                )

        # Out of turns. Say so rather than returning the last half-finished thought,
        # because the supervisor would otherwise report it as a completed action.
        yield from self._answer(
            "I could not finish this within my step limit. Ask me for a smaller piece "
            "of it, or name the case directly.",
        )

    def _answer(self, text: str) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Emit the final answer: a text delta, then the completed message item.

        The delta is the one deliberate addition to the canonical shape. MLflow's
        aggregator reads only response.output_item.done and ignores deltas, so it costs
        that path nothing - but a lone done item left the Agent Bricks Supervisor
        reporting that the agent had returned nothing, which the delta fixed. Both are
        sent so neither kind of consumer is left empty-handed.
        """
        item_id = str(uuid.uuid4())
        yield ResponsesAgentStreamEvent(**self.create_text_delta(text, item_id=item_id))
        yield ResponsesAgentStreamEvent(
            type="response.output_item.done",
            item=self.create_text_output_item(text=text, id=item_id),
        )

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """
        Answer in one piece, collecting what the streaming path produces.

        Args:
            request: What the supervisor sent.

        Returns:
            Every output item the run produced, in order.
        """
        return ResponsesAgentResponse(
            output=[
                event.item
                for event in self._stream(request)
                if event.type == "response.output_item.done"
            ],
        )

    def predict_stream(
        self,
        request: ResponsesAgentRequest,
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """
        Stream the run as it happens.

        Args:
            request: What the supervisor sent.

        Yields:
            Each output item as it is produced, plus a delta for the final text.
        """
        yield from self._stream(request)
