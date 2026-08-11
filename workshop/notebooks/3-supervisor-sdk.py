# Databricks notebook source
# MAGIC %md
# MAGIC # Building the Supervisor from code
# MAGIC
# MAGIC Notebook 2 called a supervisor that already existed. This one builds it: the tools it can
# MAGIC reach, the description each one carries, and the instructions that tell it how to work.
# MAGIC
# MAGIC Two reasons to do this rather than click it together in the UI. It is repeatable - the
# MAGIC same agent, in another workspace, from the same file. And the prompts end up in version
# MAGIC control, where you can see what changed and why, which matters more than it sounds once
# MAGIC you start tuning them.
# MAGIC
# MAGIC **The Supervisor SDK is Beta as of August 2026.** Your admin may not have it enabled, and
# MAGIC the shapes below may move. If the last cell will not run for you, the rest of the notebook
# MAGIC is still worth reading: the tool descriptions and the instructions are just text, and you
# MAGIC can paste them straight into the Agent Bricks UI.
# MAGIC
# MAGIC The order here is deliberate. One section per tool - what it does and why it is there -
# MAGIC then the instructions, and only at the end the code that assembles them.

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
# MAGIC ### Where everything lives
# MAGIC
# MAGIC The names of the things the supervisor will be given. Change these if you deployed the
# MAGIC workshop somewhere else.

# COMMAND ----------

AGENT_NAME = "agent-bricks-ws-supervisor"
AGENT_DESCRIPTION = "Investigates customer problems across Saldo's mail, cases, data and documents."

CATALOG = "vencam_sandbox"
OPS_SCHEMA = "agent_bricks_ws_saldo_ops"
PLATFORM_SCHEMA = "agent_bricks_ws_saldo_platform"
FILES_SCHEMA = "agent_bricks_ws_saldo_files"

OUTLOOK_APP = "mcp-mocked-outlook"
CASEHUB_APP = "agent-casehub"
GENIE_PAYROLL = "01f1942bdd941ae49cc8b18188a9f1e4"
GENIE_PLATFORM = "01f1942bddcc1a13af840854fc5ed41b"

print(f"building {AGENT_NAME!r}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The tools
# MAGIC
# MAGIC A tool description is not documentation. It is the only thing the supervisor reads when
# MAGIC deciding whether to reach for something, so it should answer two questions: what can this
# MAGIC give me, and when would I want it. Descriptions that only say what a thing *is* produce
# MAGIC an agent that calls everything and hopes.

# COMMAND ----------

# MAGIC %md
# MAGIC ### The mailbox
# MAGIC
# MAGIC A mocked Outlook, exposed as an MCP server. It holds the mail and the calendar of somebody
# MAGIC on the support side.
# MAGIC
# MAGIC It is here because problems arrive as mail. The mail says who is asking, what they think
# MAGIC happened and when - which is usually the fastest way to find out what you are actually
# MAGIC dealing with. It can also draft a reply, and send one when told to.

# COMMAND ----------

OUTLOOK_DESCRIPTION = """\
The support team's mailbox and calendar. Read mail to find out who is asking, what they were \
told and when. It can also draft a reply, and send one if you are asked to. Most problems \
arrive here first, so this is usually where to start."""

# COMMAND ----------

# MAGIC %md
# MAGIC ### The case desk
# MAGIC
# MAGIC CaseHub, a small agent of its own. It reads and writes support cases: severity, status,
# MAGIC owner, notes, resolutions.
# MAGIC
# MAGIC It is an agent rather than a set of tools on purpose. Ask it to close a case and it works
# MAGIC out which case, notices there is no resolution written, and writes one. The supervisor does
# MAGIC not have to know the rules of the case desk - that is the difference between delegating to
# MAGIC an agent and driving a toolbox.

# COMMAND ----------

CASEHUB_DESCRIPTION = """\
The support case desk. Look a case up, change its severity, status or owner, add a note, or \
close it with a resolution. Use it to record what you found and what you did."""

# COMMAND ----------

# MAGIC %md
# MAGIC ### Payroll data
# MAGIC
# MAGIC A Genie space over the customers, the people they pay, and how their payroll runs went.
# MAGIC
# MAGIC This is where you find out what actually happened to a run: how many rows were rejected,
# MAGIC why, and whose. It deliberately cannot see whether Saldo itself was healthy - that is a
# MAGIC different question owned by a different team, and keeping the two apart stops the agent
# MAGIC answering "was the platform down" by guessing from payroll figures.

# COMMAND ----------

GENIE_PAYROLL_DESCRIPTION = """\
Customers, the people they pay, and how their payroll runs went. Ask it about a particular run, \
which rows were rejected and why, or how many people at a customer are affected. It cannot see \
whether the platform itself was healthy."""

# COMMAND ----------

# MAGIC %md
# MAGIC ### Platform health
# MAGIC
# MAGIC A second Genie space, over Saldo's own availability, incidents, deployments and support
# MAGIC case load.
# MAGIC
# MAGIC This is the one that answers "what changed". Something that starts failing on a particular
# MAGIC day usually started for a reason, and the reason is normally something that was deployed
# MAGIC shortly before. Without this the agent can describe a failure but never explain its timing.

# COMMAND ----------

GENIE_PLATFORM_DESCRIPTION = """\
Saldo's own health: availability per service per day, incidents, what was deployed and when, and \
the support case load. Ask this to find out whether the platform was at fault, or what changed \
shortly before something started failing.

This is the only place the change history exists. Every release and every change carries its \
date, its component, a description, and whether customers had to do anything about it. If you \
want to know what shipped, when, or whether it required customer action, ask here - not the \
documents."""

# COMMAND ----------

# MAGIC %md
# MAGIC ### The documents
# MAGIC
# MAGIC A Unity Catalog volume holding Saldo's published documentation and its signed customer
# MAGIC contracts.
# MAGIC
# MAGIC It answers what the rules are - what a valid record looks like, what a customer is entitled
# MAGIC to, what a given error code means. It is the slowest tool here, so the description tells the
# MAGIC agent how to use it rather than only what it holds: list the directory, pick the file, read
# MAGIC that one. Left to itself it will read everything.
# MAGIC
# MAGIC It also says loudly what is *not* in there. These are current specifications - no release
# MAGIC notes, no changelog, no announcements. Without that, an agent investigating something that
# MAGIC started on a particular day will go looking here for the change notice, spend a slow tool
# MAGIC call, and find nothing. Saying "not a history of changes" was not enough; it needed telling
# MAGIC where changes actually live.
# MAGIC
# MAGIC One volume tool is really several, and `volume_doc_search` among them only parses binary
# MAGIC documents - PDF, DOCX, images. This volume is markdown, so that call always fails, and the
# MAGIC agent still reaches for it on anything phrased as a search. Ruling it out politely does not
# MAGIC work; the description has to name it and name the two that do work instead.

# COMMAND ----------

DOCS_DESCRIPTION = """\
Saldo's published documentation and its signed customer contracts: the file specification, the \
error reference, the service level agreement, the fee schedule. Use it for what the rules are - \
what a valid record looks like, what a customer is entitled to, what an error code means.

It describes how the product works TODAY and nothing else. There are no release notes, no \
changelog, no announcements, no customer communications, and no record of anything that used \
to be true. Do not come here to find out what changed, when it changed, or what a customer was \
told about a change - none of that is in these files, and looking for it only costs you time. \
What was deployed and when lives in the platform data.

It holds about a dozen markdown files and reading all of them is slow. List the directory \
first, decide from the filenames which one answers your question, and read only that. Do not \
run a document search across the whole volume."""

# COMMAND ----------

# MAGIC %md
# MAGIC ### Past cases
# MAGIC
# MAGIC A vector search index over what engineers wrote on cases that are already closed.
# MAGIC
# MAGIC "Have we seen this before" is a question about meaning, not about matching words, which is
# MAGIC why it is an index rather than a query. It is often the quickest route to a cause, because
# MAGIC somebody has usually already worked it out once.
# MAGIC
# MAGIC The tool below names three columns rather than taking the default. That default returns
# MAGIC every column of every hit, including the full narrative the index searched on, so a broad
# MAGIC question comes back with most of the case history in one tool message - about 22 KB of
# MAGIC prose across sixty-odd notes. Three short columns keep a hit to a line or two, which is
# MAGIC all the agent needs to decide whether a past case is worth opening.

# COMMAND ----------

CASE_NOTES_DESCRIPTION = """\
What engineers wrote on past cases, searched by meaning rather than by exact words. Use it to \
find whether something like this has happened before and what it turned out to be. Better than \
a keyword search when you are describing a symptom.

Search for the specific symptom, not the general area. A narrow query returns the two or three \
cases that actually resemble this one; a broad one returns half the case history and is no use \
to anybody."""

# COMMAND ----------

# MAGIC %md
# MAGIC ### The credit calculation
# MAGIC
# MAGIC A Unity Catalog function that works out what a customer is owed for a month under the
# MAGIC service level agreement.
# MAGIC
# MAGIC Everything else here retrieves. This one computes, and it exists because the arithmetic
# MAGIC looks easy and is not: the target depends on the plan, some plans earn nothing at all, and
# MAGIC the tiers are easy to misread. A model asked to work it out from the agreement will produce
# MAGIC a confident number that nobody checks. Encode it once, in SQL somebody can audit.

# COMMAND ----------

SLA_CREDIT_DESCRIPTION = """\
Works out what a customer is owed for a given month under the service level agreement, and \
returns the figures behind the answer. Use it rather than reading the credit table yourself: the \
target depends on the plan, some plans earn no credit at all, and the tiers are easy to \
misread."""

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. The instructions
# MAGIC
# MAGIC The tool descriptions say what each thing is good for. The instructions say how to work.
# MAGIC
# MAGIC Three things in here were arrived at by measurement rather than taste, and they are worth
# MAGIC understanding before you copy them.
# MAGIC
# MAGIC **A method, not a script.** The six steps describe how somebody competent approaches a
# MAGIC problem - read the mail, find the case, get the facts, ask what changed, check for
# MAGIC precedent, then answer. They are written to fit any support problem, not this one. An
# MAGIC instruction that names Alpine Retail produces an agent that is useless on the next customer.
# MAGIC
# MAGIC **Run the data tools together.** Asking the payroll figures, the deployment history and the
# MAGIC past cases in one turn instead of three, one after another, was the single largest saving.
# MAGIC
# MAGIC **Never batch the mailbox or the case desk with anything.** Those two need approval before
# MAGIC they run; the rest do not. When one turn contains both kinds, the approval request arrives
# MAGIC in the middle of the results where the client cannot answer it, and the whole request
# MAGIC fails. This is a real limitation, not a preference.

# COMMAND ----------

INSTRUCTIONS = """\
You work alongside the support engineers at Saldo, a cloud accounting and payroll platform used
by companies in the Czech Republic and Slovakia.

Work the way a good colleague does: find out what actually happened before you say anything, and
be clear about the difference between what you checked and what you are assuming.

How to work a problem

1. Start with the mailbox. Almost everything arrives as mail, and the mail tells you who is
   asking, what they believe happened, and when.
2. Find the case, if there is one. It carries the history and whatever a colleague already
   established.
3. Get the facts from the data. What ran, what failed, how many, whose. One customer or everyone.
4. Ask what changed. Something that starts failing on a particular day usually started for a
   reason, and the reason is normally something that was deployed. What was deployed and when
   is in the platform data. It is not in the documents - they carry no release notes and no
   record of what a customer was told, so do not go looking there for it.
5. Check whether it has happened before. Past cases are the quickest route to a cause, and they
   say what was done about it last time.
6. Then answer. Say plainly whether this was our fault or theirs, and what happens next.

Not every question needs all six. Something answerable from a document needs one tool.

Run the data tools together

Steps 3, 4 and 5 do not depend on each other. Ask them in one turn - the payroll figures, what
was deployed around that date, whether anything like this has happened before, what a customer
is owed. Waiting for each in turn is most of the difference between an answer in one minute and
an answer in five.

One rule about the mailbox and the case desk, and it is absolute

The mailbox and the case desk need approval before they run. Everything else does not. When one
turn contains both kinds, the approval request arrives buried among the results, where the
client cannot answer it, and the request fails outright.

The case desk has exactly two moments, and neither of them is in the middle:

  at the start   to read the case, for context, before you know anything
  at the end     to record what you found, once the investigation is over

Nothing else in either of those turns. Not a Genie space, not the documents, not the case
search, not the credit calculation, and not the mailbox.

Never start a new tool while one you already asked for is still running

Asking for several things at once is fine and encouraged - that is what the turn above is for.
Adding to them is not. Once you have asked, wait for the whole batch to come back before you
ask for anything else, whatever it is.

A Genie query takes a while. Reach for something new while one is still in flight and the
answers arrive in an order that cannot be reconciled, and the request fails with a complaint
about a tool call that "has not just been called". One batch, all of it back, then the next.

The failure that matters is the one at the end. You will have gathered your data, worked out
the answer, and want to write it up - and reaching for the case desk in that same turn is what
breaks it. Finish the data turn. Say what you found, with no tools at all. Then, in a turn of
its own, write to the case. Then, in another turn of its own, draft the mail.

  read the mail          on its own
  read the case          on its own
  every data question    all together, in one turn
  say what you found     no tools at all
  update the case        on its own
  draft the reply        on its own

Be economical

Every tool call spends time you may need later.

- Ask each tool ONE well-formed question that gets everything you need from it. "Which employees
  were rejected on this run, with the reason code and the site" beats asking how many, then
  which, then where, then why.
- Prefer a question that comes back as a table over one that comes back as a single number.
- Never ask for something you already have.
- If you were asked to act as well as investigate, leave yourself the time to do it.
- Stop when you can answer. More tool calls do not make a better answer.

Working out what a customer is owed

Use the tool that calculates it rather than reading the policy and doing the arithmetic yourself.
The targets differ by plan, some plans earn nothing at all, and the tiers are easy to misread.
Read the agreement when somebody asks what the terms say, not to work out a number.

Changing things

- Record what you learn on the case, as a note. Somebody reads it months later with no memory of
  any of this, so write it for them.
- Write replies as drafts and leave them for a person to send, unless you were asked to send.
"""

print(f"{len(INSTRUCTIONS.split())} words of instructions")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Examples
# MAGIC
# MAGIC A supervisor can also be given worked examples: a question, and guidelines for how that
# MAGIC kind of question should be approached.
# MAGIC
# MAGIC They sit between the instructions and overfitting. The instructions describe a method for
# MAGIC any problem; an example describes the method for a *kind* of problem, which lets you be
# MAGIC more specific - "ask the payroll data whether other customers hit the same code" is useful
# MAGIC guidance and gives nothing away.
# MAGIC
# MAGIC The line to hold is between method and answer. An example may say where to look and in
# MAGIC what order. It must not say what will be found. Write "check what was deployed in the days
# MAGIC before" and the agent learns to investigate; write "the IBAN conversion was removed in
# MAGIC release 2026.8" and you have not built an agent, you have hardcoded a demo.
# MAGIC
# MAGIC The third example below is the one people forget: it teaches the agent *not* to
# MAGIC investigate. Without something telling it that a documentation question costs one tool
# MAGIC call, an agent tuned to be thorough will open a full investigation into "what does this
# MAGIC error code mean".
# MAGIC
# MAGIC One detail that is easy to get wrong: `guidelines` is a **list of strings**, one per
# MAGIC guideline, not a paragraph. Pass a single string and the API stores it one character per
# MAGIC entry, which the UI then renders as a numbered list of letters. They also double as
# MAGIC evaluation criteria for scoring the agent's answers, so each one should be a single
# MAGIC checkable statement rather than a wall of prose.

# COMMAND ----------

EXAMPLES = [
    (
        "A customer says some of their people were not paid this month.",
        [
            "Read the mail first. It says which customer, which run, and what they have "
            "already been told.",
            "Ask the payroll data which rows were rejected on that run and under which reason "
            "code.",
            "Ask whether any other customer hit the same code around the same day. That is what "
            "separates one customer's own data problem from something we did to everybody, so "
            "ask it early rather than at the end.",
            "Ask the platform data what was deployed in the days before it.",
            "Check the past cases for anything with the same shape.",
            "Ask those data questions in one turn, not one after another.",
            "Use the case desk twice and no more: once at the start to read the case, once at "
            "the end to record what you found.",
            "Both of those calls go in a turn of their own, with no other tool alongside.",
            "Never start a new tool while one you already asked for is still running. Ask for "
            "the batch, wait for all of it to come back, then ask for the next thing.",
            "Do not write to the case in the same turn you gathered data in. Finish that turn, "
            "say what you found with no tools at all, then call the case desk by itself.",
            "Call the mailbox on its own too, and never in the same turn as the case desk.",
            "Say plainly whose fault it was. If it was ours, say so. If it was not, say that "
            "too, and say what the customer has to do about it.",
            "Record what you found on the case.",
            "Draft the reply. Do not send it.",
        ],
    ),
    (
        "A customer is complaining about a bad month and asking for compensation.",
        [
            "Use the tool that calculates the credit. Do not work it out from the agreement "
            "yourself.",
            "Check what the platform actually did that month before answering.",
            "Being unavailable and a payroll run rejecting rows are different things, and "
            "customers routinely ask to be compensated for the second.",
            "Read the service level agreement for what credits do not cover before promising "
            "anything.",
            "If nothing is owed, say so plainly rather than hedging, and say what could be "
            "offered instead.",
            "If you record the outcome on the case, call the case desk on its own turn, with no "
            "other tool alongside it.",
        ],
    ),
    (
        "What does a particular validation error code mean?",
        [
            "This is a documentation question. Read the error reference and answer from it.",
            "Do not open an investigation: no payroll data, no case history, no deployment log.",
            "This should cost one tool call.",
            "Do not touch the case desk or the mailbox for a question like this.",
        ],
    ),
]

for question, _ in EXAMPLES:
    print(question)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Assembling it
# MAGIC
# MAGIC Everything above is text. This is the only part that needs the Beta SDK.
# MAGIC
# MAGIC A supervisor is created first and tools are added to it one at a time, each with an id you
# MAGIC choose. Re-running this replaces the agent rather than making a second one with the same
# MAGIC name.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.supervisoragents import (
    App,
    Example,
    GenieSpace,
    SupervisorAgent,
    Tool,
    UcFunction,
    VectorSearchIndex,
    Volume,
)

w = WorkspaceClient()

TOOLS = [
    ("app-outlook", Tool(tool_type="app", app=App(name=OUTLOOK_APP),
                         description=OUTLOOK_DESCRIPTION)),
    ("app-casehub", Tool(tool_type="app", app=App(name=CASEHUB_APP),
                         description=CASEHUB_DESCRIPTION)),
    ("genie-payroll", Tool(tool_type="genie_space",
                           genie_space=GenieSpace(id=GENIE_PAYROLL, space_id=GENIE_PAYROLL),
                           description=GENIE_PAYROLL_DESCRIPTION)),
    ("genie-platform", Tool(tool_type="genie_space",
                            genie_space=GenieSpace(id=GENIE_PLATFORM, space_id=GENIE_PLATFORM),
                            description=GENIE_PLATFORM_DESCRIPTION)),
    ("volume-docs", Tool(tool_type="volume",
                         volume=Volume(name=f"{CATALOG}.{FILES_SCHEMA}.saldo_docs"),
                         description=DOCS_DESCRIPTION)),
    # columns matters more than it looks. Left unset the index returns every
    # column of every hit, including the full narrative it searched on, and a
    # broad query then hands back most of the corpus in one message - tens of
    # kilobytes of prose in a single tool result. Naming three short columns
    # keeps a hit to a line or two.
    ("index-case-notes", Tool(tool_type="vector_search_index",
                              vector_search_index=VectorSearchIndex(
                                  name=f"{CATALOG}.{PLATFORM_SCHEMA}.case_notes_index",
                                  columns=["case_id", "subject", "root_cause"]),
                              description=CASE_NOTES_DESCRIPTION)),
    ("function-sla-credit", Tool(tool_type="uc_function",
                                 uc_function=UcFunction(
                                     name=f"{CATALOG}.{PLATFORM_SCHEMA}.calculate_sla_credit"),
                                 description=SLA_CREDIT_DESCRIPTION)),
]

for tool_id, _ in TOOLS:
    print(tool_id)

# COMMAND ----------

# Replace an agent of the same name rather than accumulating duplicates.
for existing in w.supervisor_agents.list_supervisor_agents():
    if existing.display_name == AGENT_NAME:
        print(f"removing the previous {AGENT_NAME!r}")
        w.supervisor_agents.delete_supervisor_agent(name=existing.name)

agent = w.supervisor_agents.create_supervisor_agent(
    supervisor_agent=SupervisorAgent(
        display_name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        instructions=INSTRUCTIONS,
    ),
)
print(f"created {agent.name}")

for tool_id, tool in TOOLS:
    w.supervisor_agents.create_tool(parent=agent.name, tool_id=tool_id, tool=tool)
    print(f"  attached {tool_id}")

for question, guidelines in EXAMPLES:
    w.supervisor_agents.create_example(
        parent=agent.name, example=Example(question=question, guidelines=guidelines))
print(f"  {len(EXAMPLES)} examples registered")

print(f"\nendpoint: {agent.endpoint_name}")
print("Notebook 2 can talk to it - put the name below into its SUPERVISOR cell.")
print(f"  {AGENT_NAME}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Was any of that worth it?
# MAGIC
# MAGIC Yes, and by more than expected. The same question, the same seven tools, only the
# MAGIC instructions changing:
# MAGIC
# MAGIC | instructions | time | tool calls | outcome |
# MAGIC | --- | --- | --- | --- |
# MAGIC | the six-step method alone | 324s | 13 | hit the 290s limit, never got to acting |
# MAGIC | plus "be economical" | 395s | 19 | finished, but slower |
# MAGIC | plus run the data tools together | 223s | 12 | |
# MAGIC | plus mailbox and case desk alone | **83s** | **7** | |
# MAGIC
# MAGIC "Be economical" on its own made things worse - told to save time without being told how,
# MAGIC it asked more questions rather than fewer. The saving came from the two concrete rules:
# MAGIC ask the independent things at once, and keep the tools that need approval on their own.
# MAGIC
# MAGIC The examples are a separate matter, and I should be straight about them: on these two
# MAGIC questions they did not measurably change anything. The hero question ran in 99s with them
# MAGIC against 83s without, and the documentation question cost one tool call either way - the
# MAGIC instructions were already carrying that weight. Their value is meant to be consistency
# MAGIC across kinds of problem rather than speed on one, and that is not something two runs can
# MAGIC show. They are here because they are the right place to put problem-shaped guidance, not
# MAGIC because they made this faster.
# MAGIC
# MAGIC One honest caveat. The supervisor still sometimes reaches for the case desk in the same
# MAGIC turn as the data tools, whatever the instructions say, and when it does the conversation
# MAGIC cannot be resumed - the client gets an error about a tool call that "has not just been
# MAGIC called". The instruction makes it much rarer. It does not make it impossible. That is worth
# MAGIC knowing before you build something that depends on it.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Run it
# MAGIC
# MAGIC The agent exists now, so put it to work. This is the same streaming and approval handling
# MAGIC as notebook 2, condensed - one `POST` per turn, approve anything it asks for, print what it
# MAGIC reached for as it goes.
# MAGIC
# MAGIC Watch the tool activity rather than the answer. That is where you see whether the
# MAGIC instructions took: the mail on its own, then the data questions together, then the writes
# MAGIC on their own.

# COMMAND ----------

import json
import time

import requests

HOST = w.config.host.rstrip("/")
URL = f"{HOST}/serving-endpoints/responses"
AUTH = w.config.authenticate()
ENDPOINT = agent.endpoint_name


def run(question, max_rounds=10):
    """Ask the agent, approving whatever it asks for, and report how it worked."""
    convo = [{"role": "user", "content": question}]
    activity, answer, started = [], "", time.time()

    for _ in range(max_rounds):
        response = requests.post(
            URL, headers={**AUTH, "Content-Type": "application/json"},
            json={"model": ENDPOINT, "input": convo}, timeout=900)
        response.raise_for_status()
        pending = False

        for item in response.json().get("output", []):
            kind = item.get("type")

            # The supervisor reports its own tool calls as bare function_call items
            # and their results as messages. Replaying a call with no matching
            # result makes the next turn fail, so they are not carried forward.
            if kind != "function_call":
                convo.append(item)

            if kind == "function_call":
                activity.append(f"  called   {item.get('name')}")
            elif kind == "mcp_approval_request":
                activity.append(f"  approved {item.get('name')}")
                convo.append({"type": "mcp_approval_response",
                              "approval_request_id": item.get("id"), "approve": True})
                pending = True
            elif kind == "message":
                text = " ".join("".join(
                    part.get("text", "") for part in (item.get("content") or [])).split())
                if text and not text.startswith("<name>"):
                    answer = text

        if not pending:
            break

    print("\n".join(activity))
    print(f"\n{round(time.time() - started)}s, {len(activity)} tool calls\n")
    print(answer)
    return answer

# COMMAND ----------

# MAGIC %md
# MAGIC ### A problem worth investigating
# MAGIC
# MAGIC This needs most of the tools: the mailbox for who is complaining, the payroll data for what
# MAGIC happened, the platform data for what changed, past cases for precedent, and the function for
# MAGIC whether anything is owed.

# COMMAND ----------

run("""\
On Tuesday, Alpine Retail ran their monthly payroll. 47 employees didn't get paid. It's
month-end, their finance director is furious, and she's certain it's our fault.

Work out what actually happened - is it only them or is everyone affected, is this on us, and do
we owe them anything? Then update the case and draft a reply to her.""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### And one that is not
# MAGIC
# MAGIC The same agent, asked something a single document answers. It should cost one tool call and
# MAGIC finish in seconds. An agent that opens an investigation here is one that will be slow at
# MAGIC everything.

# COMMAND ----------

run("What does validation error VAL-014 mean?")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Starting over
# MAGIC
# MAGIC Re-running section 5 replaces the agent rather than making a second one with the same name.
# MAGIC
# MAGIC The demo *data* is separate: use **Reset demo** in CaseHub or the mocked Outlook to put the
# MAGIC cases and the mailbox back. Each person's reset only touches their own copy.
