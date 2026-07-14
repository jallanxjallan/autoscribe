# Autoscribe Client Agent Architecture

## Decision

Extract the business logic from the current CLI package and expose it through two primary interfaces:

1. **CLI**
   - Full administrative interface for the operator/sysadmin.
   - Optional smaller subset for technically inclined users.

2. **Autoscribe client agent**
   - Conversational interface inside Electron.
   - Guides users in using Autoscribe.
   - Translates prose or voice-style requests into structured selections, instructions, plans, commits, and dispatch requests.

Both interfaces must call the same underlying application services. Neither should contain the actual business logic.

---

## Core Principle

The CLI and the agent are not separate implementations of Autoscribe.

They are adapters over one shared command and service layer:

```text
CLI commands ───────────┐
                        ├── Autoscribe application services
Agent tools ────────────┤
                        └── Electron forms and buttons
```

A function that performs an Autoscribe operation must be callable without:

- a terminal,
- Electron,
- an OpenAI model,
- or a chat interface.

---

## Architectural Layers

### 1. Domain Layer

Defines Autoscribe’s core objects and validation rules.

Likely objects include:

- `Selection`
- `Instruction`
- `Plan`
- `PlanStep`
- `CommitRequest`
- `DispatchRequest`
- `WritebackRequest`
- corresponding result objects

This layer should know nothing about:

- Typer,
- terminal output,
- Electron,
- IPC,
- OpenAI,
- conversational history,
- or UI formatting.

Pydantic models remain the authoritative schemas for structured requests and results.

---

### 2. Application / Service Layer

Implements the actual Autoscribe use cases.

Examples:

- preview a selection,
- save a selection,
- create or update an instruction,
- create or update a plan,
- inspect Git state,
- commit selected files,
- dispatch a selection against a plan,
- inspect pending calls,
- apply writeback,
- record results in the ledger.

A service receives a typed request and returns a typed result.

Example:

```python
class DispatchService:
    def execute(self, request: DispatchRequest) -> DispatchResult:
        selection = self.selections.resolve(request.selection_identity)
        plan = self.plans.resolve(request.plan_identity)
        commit = self.git.commit(selection, request.commit)
        calls = self.pipeline.dispatch(selection, plan)

        return DispatchResult(
            selection_identity=selection.identity,
            plan_identity=plan.identity,
            commit_hash=commit.hash,
            call_identities=calls,
        )
```

The service owns the workflow. It does not print terminal messages or generate conversational prose.

---

### 3. Infrastructure Adapters

Connect the service layer to concrete systems.

Examples:

- filesystem and frontmatter,
- Git,
- SQLite ledger,
- Redis,
- remote pipeline upload,
- Obsidian helpers,
- later Electron-local state.

These adapters can change without changing the CLI or agent contracts.

---

### 4. Interface Adapters

Expose application services to users or other programs.

#### CLI adapter

The CLI should become thin:

```python
@app.command()
def dispatch(...):
    request = DispatchRequest(...)
    result = dispatch_service.execute(request)
    print_dispatch_result(result)
```

Its responsibilities are limited to:

- parsing command-line arguments,
- creating typed request objects,
- invoking services,
- formatting results for the terminal,
- choosing appropriate exit codes.

#### Agent tool adapter

The client agent exposes narrow, structured tools:

```python
def agent_dispatch(arguments: dict) -> dict:
    request = DispatchRequest.model_validate(arguments)
    result = dispatch_service.execute(request)
    return result.model_dump(mode="json")
```

Its responsibilities are limited to:

- accepting validated tool arguments,
- invoking the same services as the CLI,
- returning structured JSON to the model,
- enforcing approval and permission rules.

#### Electron UI adapter

Forms, buttons, checkboxes, and previews should also call the same services through IPC.

The graphical interface and conversational interface must not implement separate selection, plan, Git, or dispatch logic.

---

## Agent Role

The agent is a conversational controller and compiler, not a second orchestrator.

It has two main functions:

### Guidance

Explain:

- Autoscribe concepts,
- status, stage, origin, and Git state,
- selections,
- instructions,
- plans,
- commits,
- dispatch,
- review and writeback workflows.

### Intent Translation

Convert prose or transcribed voice requests into structured requests.

Example user request:

> Take the HHP passages I edited today, give them a light cleanup, preserve my voice, and send them for review.

The agent first interprets the request semantically:

```yaml
scope:
  project: HHP
  repo_state:
    - editing
  changed_since: today

operations:
  - line_edit

constraints:
  preserve_voice: true
  review_required: true
```

It then uses read-only tools to resolve that intent against live Autoscribe state:

- find matching files,
- find suitable existing instructions,
- find a matching plan,
- inspect Git state,
- validate the proposed operation.

Only then does it produce an executable request using real identities.

---

## No Manifest Type for Every Phrase

Autoscribe does not need a distinct YAML file for every possible user operation or wording.

Use:

1. a small command vocabulary,
2. typed request models,
3. discriminated command payloads,
4. persistent files only where persistence is useful.

Likely command families:

- `select`
- `inspect`
- `save_instruction`
- `save_plan`
- `commit`
- `dispatch`
- `writeback`

An in-memory command envelope may look like:

```yaml
action: dispatch
payload:
  selection_identity: sel.abc
  plan_identity: plan.xyz
  write_mode: replace
  review_required: true
```

In Python, this can become a discriminated union:

```python
Command = Annotated[
    SelectCommand
    | SaveInstructionCommand
    | SavePlanCommand
    | CommitCommand
    | DispatchCommand
    | WritebackCommand,
    Field(discriminator="action"),
]
```

Most intermediate objects should remain ephemeral JSON passed between Electron and Python.

Persist only objects worth keeping, inspecting, committing, or reusing:

- instructions,
- plans,
- saved selections,
- commit records,
- dispatch and ledger records.

---

## Voice Commands

Voice does not require a separate Autoscribe architecture.

The flow is:

```text
microphone audio
    ↓
speech-to-text
    ↓
ordinary prose request
    ↓
agent intent interpretation
    ↓
tool-based resolution
    ↓
validated Autoscribe command
```

Speech-to-text only transcribes. The agent performs semantic interpretation.

---

## Approval Boundaries

Agent tools should be grouped by consequence.

### Read-only

May usually run without confirmation:

- inspect current document,
- preview a selection,
- list or read instructions,
- list or read plans,
- inspect Git state,
- inspect calls and pending results,
- explain Autoscribe concepts.

### Reversible draft operations

May require a visible acknowledgement:

- save a selection,
- save an instruction draft,
- save a plan draft,
- change UI filters,
- update draft metadata.

### Consequential operations

Require explicit approval:

- commit files,
- amend or truncate a commit,
- dispatch calls,
- overwrite files,
- apply writeback,
- delete persistent records,
- publish or export externally.

The model proposes and explains. Autoscribe validates and executes.

---

## Different Interfaces, Different Exposure

The same services can be exposed differently.

### Administrative CLI

May expose low-level and recovery operations:

```text
asc storage ...
asc run ...
asc inspect ...
asc repair ...
asc reset ...
asc upload ...
```

### User-facing CLI subset

May expose only stable workflows:

```text
asc select
asc plan
asc commit
asc dispatch
asc pending
asc writeback
```

### Agent interface

Should expose a curated collection of narrow tools rather than unrestricted shell-style commands.

The agent should never receive a general-purpose “run command” or arbitrary-script tool for routine operation.

---

## Shared Request and Result Models

Every operation should accept and return structured objects.

Example request:

```python
class DispatchRequest(BaseModel):
    selection_identity: str
    plan_identity: str
    commit_label: str
    commit_note: str | None = None
    write_mode: Literal["replace", "append"]
    review_required: bool
```

Example result:

```python
class DispatchResult(BaseModel):
    selection_identity: str
    file_count: int
    commit_hash: str
    plan_identity: str
    call_identities: list[str]
```

The interfaces present that result differently:

- CLI prints terminal text.
- Electron renders a result card.
- The agent explains it conversationally.

Presentation must remain outside the service layer.

---

## Suggested Package Shape

```text
autoscribe/
├── domain/
│   ├── selection.py
│   ├── instruction.py
│   ├── plan.py
│   ├── commit.py
│   ├── dispatch.py
│   └── writeback.py
│
├── services/
│   ├── selections.py
│   ├── instructions.py
│   ├── plans.py
│   ├── commits.py
│   ├── dispatch.py
│   └── writeback.py
│
├── ports/
│   ├── git.py
│   ├── repository.py
│   ├── pipeline.py
│   └── ledger.py
│
├── adapters/
│   ├── filesystem.py
│   ├── git_cli.py
│   ├── redis_pipeline.py
│   ├── sqlite_ledger.py
│   └── obsidian.py
│
└── interfaces/
    ├── cli/
    ├── ipc/
    └── agent/
```

The exact names can remain informal. The important boundary is that business operations are independent of their interface.

---

## Migration Sequence

### Phase 1: Identify mixed CLI functions

Find CLI commands that currently combine:

- argument parsing,
- file selection,
- Git operations,
- manifest construction,
- upload or dispatch,
- printing,
- and error handling.

### Phase 2: Extract typed request and result models

Create explicit Pydantic objects for each stable use case.

Start with the operations already working in the CLI:

- instruction upload,
- plan upload,
- selection,
- commit,
- dispatch,
- writeback.

### Phase 3: Extract services

Move operational logic out of Typer commands.

The original CLI command should become a thin wrapper around one service call.

### Phase 4: Add IPC interface

Expose the same services to Electron through structured JSON requests and responses.

### Phase 5: Build ordinary Electron controls

Have forms and buttons call the service layer through IPC.

This proves the application boundary before adding an agent.

### Phase 6: Add read-only agent tools

Begin with:

- preview selection,
- list instructions,
- read instruction,
- list plans,
- read plan,
- inspect Git state.

### Phase 7: Add drafting tools

Add:

- validate instruction draft,
- save instruction draft,
- validate plan draft,
- save plan draft,
- save selection.

### Phase 8: Add approved consequential tools

Finally add:

- commit selection,
- dispatch selection,
- apply writeback.

These tools should require explicit user approval and return the same records as the manual interface.

---

## Final Architecture Decision

The current CLI package is the prototype application layer.

The next step is to extract its business logic into reusable services and retain the CLI as one adapter.

Autoscribe will then have:

```text
                 Autoscribe domain and services
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
     Admin/user CLI      Electron UI       Client agent
```

The client agent translates human intent into typed requests and selects tools.

Autoscribe code resolves identities, validates schemas, controls permissions, performs operations, and records the result.

The governing rule is:

> The agent determines what the user appears to want. Autoscribe determines what is valid and performs the operation.
