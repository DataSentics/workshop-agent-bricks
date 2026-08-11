# Databricks notebook source
# MAGIC %md
# MAGIC # Calling your Supervisor from code
# MAGIC
# MAGIC If you are here, you have probably just built your own supervisor in the Agent Bricks
# MAGIC UI. Congratulations. If you have not, you can point this at the pre-made one instead,
# MAGIC or jump to notebook 3 and build one in code (note that the SDK and REST API are still
# MAGIC Beta features which must be allowed by your admin as for 2026-08) rather than by clicking.
# MAGIC
# MAGIC The Agent Bricks UI gives you a fast experience for experimenting and playing around,
# MAGIC though it can still contain some bugs (as of August 2026). In reality, though, you
# MAGIC will probably want to:
# MAGIC
# MAGIC - integrate the created agent into your own UI,
# MAGIC - or integrate it without any UI at all - as part of an automated process, for example.
# MAGIC
# MAGIC The purpose of this notebook is simply to demonstrate how to invoke the created agent
# MAGIC from code. A Python example and a curl example are used. Note, though, that the
# MAGIC supervisor is nothing more than an exposed HTTPS API endpoint - any language or
# MAGIC framework can be used to interact with it.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Setup
# MAGIC
# MAGIC Since this is a demo notebook, let's make a best effort to get the environment as close
# MAGIC as possible to the one the code was written and tested in - the same Databricks SDK
# MAGIC version, and so on.

# COMMAND ----------

import shutil
import subprocess
import sys

uv = shutil.which("uv")
if uv is None:
    print("uv is not on this environment (it ships with serverless v4+); installing it")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "uv"], check=True)
    uv = shutil.which("uv") or "uv"

subprocess.run(
    [uv, "pip", "install", "--quiet", "--python", sys.executable, "-r", "./requirements.txt"],
    check=True,
)
print(f"dependencies installed with {uv}")

# COMMAND ----------

# MAGIC %restart_python

# COMMAND ----------

# MAGIC %md
# MAGIC ### Which agent, and who approves its tools
# MAGIC
# MAGIC First, name the agent you created - or the one you want to run - exactly as it appears
# MAGIC in the Agent Bricks UI.
# MAGIC
# MAGIC `AUTO_APPROVE` is worth playing with. A supervisor will not invoke another agent or an
# MAGIC MCP tool without approval first. That is useful: it is a place to put a human in the
# MAGIC loop, and to see what the agent intended to do before it does it. When you are
# MAGIC confident it is unnecessary, or you are automating something and there is no human to
# MAGIC ask, your client code can watch for those requests and approve them itself. Or apply
# MAGIC whatever rule you like - approve reads, ask about writes, refuse anything touching a
# MAGIC particular customer - completly up to your client code.

# COMMAND ----------

# As it appears in the Agent Bricks UI. Its serving endpoint name works too.
SUPERVISOR = "supervisor-agent-2026-08-09-13-58-01"

# Approve tool calls automatically. False stops and shows you what it wanted instead.
AUTO_APPROVE = True

# COMMAND ----------

import json

import requests
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()


def resolve_endpoint(name: str) -> str:
    """Accept a display name or an endpoint name, return the endpoint name.

    Agent Bricks shows you a display name; the API wants the serving endpoint
    behind it, which is a different string (`mas-<id>-endpoint`).
    """
    agents = list(w.supervisor_agents.list_supervisor_agents())
    for agent in agents:
        if name in (agent.display_name, agent.endpoint_name):
            return agent.endpoint_name
    raise SystemExit(f"No supervisor {name!r}. Found: {[a.display_name for a in agents]}")


# Also a check that the agent is really there: a typo in the name fails here, with
# a list of what does exist, rather than as a confusing error several cells later.
ENDPOINT = resolve_endpoint(SUPERVISOR)
HOST = w.config.host.rstrip("/")
URL = f"{HOST}/serving-endpoints/responses"
AUTH = w.config.authenticate()

print(f"{SUPERVISOR}\n  -> {ENDPOINT}\n  -> {URL}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Calling the deployed agent with Python
# MAGIC
# MAGIC Invoking the agent is just a `POST` to `/serving-endpoints/responses`. You specify in
# MAGIC the payload whether you want a streamed response or the whole answer in one piece.
# MAGIC
# MAGIC Please note that an agent can take quite some time to finish - several minutes is
# MAGIC normal, since it may call a number of tools along the way. When integrating this into
# MAGIC your own systems, take into account things like load balancer and gateway timeouts.
# MAGIC
# MAGIC Note as well that a long running mode - where you submit a request, receive an
# MAGIC acknowledgement id, and then poll for the result without worrying about timeouts - is
# MAGIC not available as of August 2026. But it is planned.
# MAGIC
# MAGIC A streamed reply arrives as server-sent events, one `data:` line each, ending with
# MAGIC `data: [DONE]`. Two kinds matter here: `response.output_text.delta` carries a fragment
# MAGIC of text, and `response.output_item.done` carries a finished item - a message, a tool
# MAGIC call, or a request for approval.
# MAGIC
# MAGIC **Things to be aware of**
# MAGIC
# MAGIC - **Nothing is remembered for you.** The API is stateless: you send the whole
# MAGIC   conversation every time. That is why `ask()` returns the thread and takes it back.
# MAGIC - **The approval request is not its own event type.** It arrives inside a
# MAGIC   `response.output_item.done` whose `item.type` is `mcp_approval_request`. Easy to miss
# MAGIC   if you are only watching for text, and then the agent looks like it stopped for no
# MAGIC   reason.
# MAGIC - **Your approval has to go in the right place** - directly after the request it
# MAGIC   answers, not appended at the end of the conversation. Putting it at the end looks
# MAGIC   fine and works, right up until the supervisor asks for two tools in one turn. The
# MAGIC   ungated one runs immediately, the App tool waits, and the approval request ends up
# MAGIC   in the middle. Reply at the end then and the whole call is rejected with
# MAGIC   `Invalid message sequence. The approval response was in an unexpected position.`
# MAGIC - **Approval can take more than one round.** The supervisor may ask, get approved, and
# MAGIC   then ask again - so this is a loop, not a single retry.
# MAGIC - **Only Custom Agents and MCP services are gated.** In this workshop that means CaseHub and the
# MAGIC   mocked Outlook. Genie spaces, Unity Catalog functions and volumes are called
# MAGIC   straight through with no approval at all.

# COMMAND ----------

MAX_ROUNDS = 8


def stream_once(convo):
    """One streamed call. Prints text as it arrives.

    Args:
        convo: The conversation so far.

    Returns:
        The items the supervisor produced, and the approval requests among them.
    """
    body = {"model": ENDPOINT, "input": convo, "stream": True}
    items, approvals = [], []

    with requests.post(URL, headers={**AUTH, "Content-Type": "application/json"},
                       json=body, stream=True, timeout=600) as response:
        response.raise_for_status()
        for raw in response.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            payload = raw[6:]
            if payload.strip() == "[DONE]":
                break

            event = json.loads(payload)
            kind = event.get("type")

            if kind == "response.output_text.delta":
                print(event.get("delta", ""), end="", flush=True)

            elif kind == "response.output_item.done":
                item = event.get("item") or {}
                items.append(item)
                if item.get("type") == "mcp_approval_request":
                    approvals.append(item)
                    print(f"\n  [needs approval: {item.get('name')}]")
                elif item.get("type") == "function_call":
                    print(f"\n  [tool: {item.get('name')}]")
    return items, approvals


def ask(question, convo=None):
    """Ask the supervisor and stream the answer, approving tools as it goes.

    Args:
        question: What to ask.
        convo: Pass a previous return value to carry on that conversation.

    Returns:
        The conversation, ready to pass back for a follow-up.
    """
    thread = list(convo or [])
    thread.append({"role": "user", "content": question})
    print(f"YOU: {question}\n")

    for _ in range(MAX_ROUNDS):
        items, approvals = stream_once(thread)

        for item in items:
            thread.append(item)
            # Directly after its own request, not at the end of the thread.
            if item.get("type") == "mcp_approval_request" and AUTO_APPROVE:
                thread.append({
                    "type": "mcp_approval_response",
                    "approval_request_id": item.get("id"),
                    "approve": True,
                })

        if not approvals or not AUTO_APPROVE:
            print()
            return thread

    print("\n(gave up after too many approval rounds)")
    return thread

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Ask it something
# MAGIC
# MAGIC One tool can answer this one.

# COMMAND ----------

convo = ask("What open support cases does Alpine Retail have?")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Carry on the conversation
# MAGIC
# MAGIC Pass the thread back and "that case" still means something.

# COMMAND ----------

convo = ask("What is that case actually about?", convo)

# COMMAND ----------

# MAGIC %md
# MAGIC ### The question the whole environment exists for
# MAGIC
# MAGIC No single tool answers this. It needs the case desk, the payroll data and the change
# MAGIC records, so expect it to ask for more than one of them.

# COMMAND ----------

convo = ask(
    "Alpine Retail's July payroll rejected 47 employees and the runs before it were "
    "clean. Work out why it started when it did, and tell me whether they are owed a "
    "service credit."
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Calling the deployed agent with Curl/Bash
# MAGIC
# MAGIC Nothing above needed Python. The cells below do a similar job with curl and a little
# MAGIC bash, to make the point that this is an ordinary HTTPS endpoint - anything that can
# MAGIC post JSON and read a response will do.
# MAGIC
# MAGIC Two things to know before reading them.
# MAGIC
# MAGIC There is no `jq` on serverless, so these print the raw response rather than pretending
# MAGIC to parse it. In your own environment the answer is the last message in the output
# MAGIC array, which `jq` gets at with
# MAGIC `jq -r '[.output[] | select(.type=="message")] | last | .content[0].text'`.
# MAGIC
# MAGIC And both questions here are deliberately ones the supervisor can answer from Genie.
# MAGIC A single command only works when no approval is needed - ask something that requires
# MAGIC CaseHub or the mocked Outlook and you will get an `mcp_approval_request` back instead
# MAGIC of an answer, because approving it means sending the conversation again, which is a
# MAGIC loop rather than a one-liner.

# COMMAND ----------

import os

# A %sh cell runs in a shell that inherits this process's environment, so the
# endpoint and the token get handed over without pasting either into the cells
# below, and without printing the token anywhere.
os.environ["AGENT_URL"] = URL
os.environ["AGENT_ENDPOINT"] = ENDPOINT
os.environ["AGENT_AUTH"] = AUTH["Authorization"]

print("environment ready for the shell cells")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Streamed
# MAGIC
# MAGIC `-N` turns off curl's buffering so the events arrive as they are produced. This is the
# MAGIC raw `data:` stream that `stream_once()` above was parsing for you.

# COMMAND ----------

# MAGIC %sh
# MAGIC PAYLOAD='{"model": "'"$AGENT_ENDPOINT"'", "input": [{"role": "user", "content": "Which Saldo services had availability problems in July 2026?"}], "stream": true}'
# MAGIC
# MAGIC curl -sN -X POST "$AGENT_URL" \
# MAGIC   -H "Authorization: $AGENT_AUTH" \
# MAGIC   -H "Content-Type: application/json" \
# MAGIC   -d "$PAYLOAD" | head -20

# COMMAND ----------

# MAGIC %md
# MAGIC ### Not streamed
# MAGIC
# MAGIC Leave `"stream": true` out and the whole thing comes back as one JSON document once the
# MAGIC agent has finished - simpler to handle, but you wait with nothing on screen until it is
# MAGIC done.

# COMMAND ----------

# MAGIC %sh
# MAGIC PAYLOAD='{"model": "'"$AGENT_ENDPOINT"'", "input": [{"role": "user", "content": "What changes were deployed on 1 August 2026?"}]}'
# MAGIC
# MAGIC curl -s -X POST "$AGENT_URL" \
# MAGIC   -H "Authorization: $AGENT_AUTH" \
# MAGIC   -H "Content-Type: application/json" \
# MAGIC   -d "$PAYLOAD" | head -c 1500

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Bonus: the other agents are callable too
# MAGIC
# MAGIC The supervisor is the most complex interface here, in the sense that it can encompass
# MAGIC many components. It is definitely not the only one. The Genie Agents and the custom
# MAGIC agent are services in their own right and can be called and integrated separately -
# MAGIC the supervisor is meant as an interface for combining those building blocks, not as
# MAGIC the only way in. This section shows how they are called on their own.
# MAGIC
# MAGIC The Knowledge Assistant is not repeated below: it is a serving endpoint like the
# MAGIC supervisor, so section 2 works unchanged with `model` set to `ka-<id>-endpoint`.

# COMMAND ----------

# MAGIC %md
# MAGIC ### One Genie Agent
# MAGIC
# MAGIC Genie has a Conversation API of its own rather than a serving endpoint, and the SDK
# MAGIC covers it - `w.genie`.
# MAGIC
# MAGIC - **Asynchronous.** The `*_and_wait` methods poll for you; the curl cell does not.
# MAGIC - **The answer is in the attachments**: `text` for words, `query` for SQL. The rows
# MAGIC   are fetched separately, per attachment.
# MAGIC - **The conversation lives on the server**, so you keep the `conversation_id` rather
# MAGIC   than the whole thread.

# COMMAND ----------

# As it appears in the Genie UI. The other one is "Saldo platform health".
GENIE_AGENT = "Saldo payroll operations"

space = next((s for s in (w.genie.list_spaces().spaces or []) if s.title == GENIE_AGENT), None)
if space is None:
    raise SystemExit(f"No Genie Agent {GENIE_AGENT!r} in this workspace")

SPACE_ID = space.space_id
print(f"{GENIE_AGENT}\n  -> {SPACE_ID}\n  -> {HOST}/genie/rooms/{SPACE_ID}")

# COMMAND ----------


def print_rows(statement, limit=10):
    """Print a Genie result set as a small table.

    Args:
        statement: The statement response fetched for one query attachment.
        limit: How many rows to show before summarising the rest.
    """
    columns = [c.name for c in (statement.manifest.schema.columns or [])]
    rows = (statement.result.data_array or []) if statement.result else []

    print("  " + " | ".join(columns))
    for row in rows[:limit]:
        print("  " + " | ".join("" if value is None else str(value) for value in row))
    if len(rows) > limit:
        print(f"  ... and {len(rows) - limit} more rows")


def ask_genie(question, conversation_id=None):
    """Ask one Genie Agent directly, with no supervisor in front of it.

    Args:
        question: What to ask.
        conversation_id: Pass a previous return value to carry on that conversation.

    Returns:
        The conversation id, ready to pass back for a follow-up.
    """
    print(f"YOU: {question}\n")

    if conversation_id is None:
        message = w.genie.start_conversation_and_wait(SPACE_ID, question)
    else:
        message = w.genie.create_message_and_wait(SPACE_ID, conversation_id, question)

    for attachment in message.attachments or []:
        if attachment.text:
            print(attachment.text.content)
        if attachment.query:
            print(attachment.query.description or "")
            print(f"\n  SQL: {attachment.query.query}\n")
            result = w.genie.get_message_attachment_query_result(
                SPACE_ID, message.conversation_id, message.message_id,
                attachment.attachment_id)
            print_rows(result.statement_response)

    print()
    return message.conversation_id

# COMMAND ----------

conversation = ask_genie("Which customers had payroll rejections in July 2026?")

# COMMAND ----------

# The server remembers the thread, so "them" still means something.
conversation = ask_genie("Why were they rejected?", conversation)

# COMMAND ----------

# MAGIC %md
# MAGIC ### The same in curl
# MAGIC
# MAGIC The polling the SDK hid: start, keep the two ids, re-read the message until it leaves
# MAGIC `IN_PROGRESS`. Still no `jq` on serverless, so the ids come out with `grep`.

# COMMAND ----------

import os

# Repeats the earlier environment cell as well, so this section can be run on its own.
os.environ["DBX_HOST"] = HOST
os.environ["GENIE_SPACE_ID"] = SPACE_ID
os.environ["AGENT_AUTH"] = AUTH["Authorization"]

print("environment ready for the shell cells")

# COMMAND ----------

# MAGIC %sh
# MAGIC SPACE="$DBX_HOST/api/2.0/genie/spaces/$GENIE_SPACE_ID"
# MAGIC
# MAGIC START=$(curl -s -X POST "$SPACE/start-conversation" \
# MAGIC   -H "Authorization: $AGENT_AUTH" \
# MAGIC   -H "Content-Type: application/json" \
# MAGIC   -d '{"content": "How many employees does each customer have?"}')
# MAGIC
# MAGIC CONVERSATION=$(printf '%s' "$START" | grep -oE '"conversation_id" *: *"[^"]+"' | head -1 | cut -d'"' -f4)
# MAGIC MESSAGE=$(printf '%s' "$START" | grep -oE '"message_id" *: *"[^"]+"' | head -1 | cut -d'"' -f4)
# MAGIC echo "conversation $CONVERSATION, message $MESSAGE"
# MAGIC
# MAGIC # Genie answers in seconds, but the warehouse it runs on may have to wake up first,
# MAGIC # which is what the generous ceiling here is for.
# MAGIC for _ in $(seq 1 60); do
# MAGIC   BODY=$(curl -s "$SPACE/conversations/$CONVERSATION/messages/$MESSAGE" \
# MAGIC     -H "Authorization: $AGENT_AUTH")
# MAGIC   STATUS=$(printf '%s' "$BODY" | grep -oE '"status" *: *"[^"]+"' | head -1 | cut -d'"' -f4)
# MAGIC   echo "  $STATUS"
# MAGIC   case "$STATUS" in COMPLETED|FAILED|CANCELLED|QUERY_RESULT_EXPIRED) break ;; esac
# MAGIC   sleep 5
# MAGIC done
# MAGIC
# MAGIC printf '%s' "$BODY" | head -c 1500

# COMMAND ----------

# MAGIC %md
# MAGIC ### The custom agent
# MAGIC
# MAGIC CaseHub serves `/responses` on its own host: the section 2 payload without `model`,
# MAGIC since the app itself is what you are calling. `w.apps` finds it and can start or stop
# MAGIC it, but the SDK has no method for invoking an app, so the POST stays a plain request.
# MAGIC
# MAGIC - **Nothing is gated.** Approval is supervisor behaviour. Called directly, CaseHub's
# MAGIC   tools run when it decides to - closing a case included.
# MAGIC - **Apps forwards your identity**, so changes land on your copy of the case data.
# MAGIC - **The app has to be running.** Check **Compute > Apps** if the call refuses.

# COMMAND ----------

CUSTOM_AGENT = "agent-casehub"

app = w.apps.get(CUSTOM_AGENT)
CASEHUB_URL = f"{app.url.rstrip('/')}/responses"
os.environ["CASEHUB_URL"] = CASEHUB_URL

print(f"{CUSTOM_AGENT}\n  -> {CASEHUB_URL}")

# COMMAND ----------


def ask_casehub(question, convo=None):
    """Ask the CaseHub agent directly, with no supervisor in front of it.

    Args:
        question: What to ask.
        convo: Pass a previous return value to carry on that conversation.

    Returns:
        The conversation, ready to pass back for a follow-up.
    """
    thread = list(convo or [])
    thread.append({"role": "user", "content": question})
    print(f"YOU: {question}\n")

    # Stateless in the same way the supervisor is: the whole thread goes every time.
    response = requests.post(CASEHUB_URL,
                             headers={**AUTH, "Content-Type": "application/json"},
                             json={"input": thread}, timeout=600)
    response.raise_for_status()
    output = response.json().get("output", [])

    for item in output:
        if item.get("type") == "function_call":
            print(f"  [tool: {item.get('name')}]")
        elif item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    print(part.get("text", ""))

    print()
    return thread + output

# COMMAND ----------

cases = ask_casehub("What open cases does Alpine Retail have, and who is on them?")

# COMMAND ----------

# MAGIC %md
# MAGIC ### The same in curl
# MAGIC
# MAGIC The ordinary synchronous POST again. Add `"stream": true` and `-N` for the events.

# COMMAND ----------

# MAGIC %sh
# MAGIC PAYLOAD='{"input": [{"role": "user", "content": "Summarise case CAS-40318."}]}'
# MAGIC
# MAGIC curl -s -X POST "$CASEHUB_URL" \
# MAGIC   -H "Authorization: $AGENT_AUTH" \
# MAGIC   -H "Content-Type: application/json" \
# MAGIC   -d "$PAYLOAD" | head -c 1500

# COMMAND ----------

# MAGIC %md
# MAGIC ## Starting over
# MAGIC
# MAGIC Every `ask()` without a conversation starts a fresh one - there is no session on the
# MAGIC server to clear.
# MAGIC
# MAGIC To put the demo *data* back where it started, use **Reset demo** in CaseHub or in the
# MAGIC mocked Outlook. Each person's reset only touches their own copy, so you will not
# MAGIC disturb anyone else in the room.
