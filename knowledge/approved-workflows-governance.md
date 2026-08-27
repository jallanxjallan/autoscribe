# Approved Workflows as the Universal AutoScribe Execution Model

## Position

AutoScribe should permit every user to describe any desired editorial outcome, but it should execute only nominated, approved and versioned workflows. This rule should apply equally to a corporate communications department preparing an annual report and to an individual writer producing website content for dive camps.

The scale, sensitivity and administrative setting may differ. The execution principle should not.

> Users may request any outcome, but production processing must use an approved plan.

This preserves the convenience of a conversational agent without allowing free-form instructions to assemble untested pipeline machinery at runtime.

## Why free-form agent execution is the wrong default

A conversational interface naturally encourages users to believe that describing a task and executing it are the same operation. In a production pipeline, they must remain distinct.

An unrestricted agent might choose different models, introduce unfamiliar instructions, omit required checks, send material to an unapproved service, change writeback behaviour or create an expensive and irreproducible sequence of operations. Even when the result appears satisfactory, neither the user nor the operator can reliably establish what happened or repeat it later.

This is undesirable for an enterprise because it creates security, compliance and audit problems. It is equally undesirable for a small commercial user because it creates unpredictable costs, inconsistent quality and support requests that cannot be reproduced.

Approved workflows are therefore not merely an enterprise restriction. They are the basic quality-control mechanism of the product.

## What the user may do

Ordinary users should be free to:

- select from plans approved for their account, project or organization;
- upload manuscripts, notes and other permitted source material;
- supply project context and bounded plan parameters;
- choose among explicitly supported output options;
- answer structural, editorial and provenance ambiguities;
- describe a new result they want;
- request a new plan or an amendment to an existing plan.

They should not be able to alter production machinery directly. In particular, ordinary users should not freely:

- add or reorder pipeline steps;
- select arbitrary models or external services;
- replace standing instructions;
- introduce executable scripts;
- change security, retention or writeback rules;
- redirect outputs to unapproved destinations;
- publish a newly generated plan directly into production.

The distinction is between controlling the work and controlling the machinery. Users should control their content and desired outcome. Authorized plan managers should control how the system produces it.

## The agent’s role

The agent remains the natural interface for custom requirements. A user might say:

> Rewrite these dive-camp pages for first-time visitors, retain all safety information, normalize the operator descriptions and produce a consistent page for each location.

Or a corporate communications user might say:

> Shorten this sustainability report for the annual-report audience and check every numerical claim against the approved spreadsheet.

The agent should compare the request with the plans available to that user. It may determine that:

1. an existing plan already covers the request;
2. an existing plan covers it with permitted parameters;
3. the request requires a controlled amendment;
4. the request requires a new plan;
5. the requested processing cannot be approved under current policy.

Where no approved plan fits, the agent should create a structured plan request—not improvise and execute a new workflow. The request should capture the intended outcome, input types, required transformations, verification needs, output format and any unusual handling constraints.

## Approval and implementation

Initially, the founder or another AutoScribe superuser may review and implement custom requests. The lifecycle should be:

1. **Requested:** the user describes the desired outcome.
2. **Interpreted:** the agent converts the conversation into a structured plan request.
3. **Reviewed:** a superuser checks scope, feasibility, risks and overlap with existing plans.
4. **Implemented:** the superuser creates or adapts the plan and its instructions.
5. **Tested:** representative material is processed and inspected.
6. **Approved:** an authorized publisher makes the plan available to the appropriate scope.
7. **Versioned:** the exact production definition becomes immutable.
8. **Monitored:** failures, costs and quality issues are reviewed.
9. **Revised or deprecated:** changes create a new version rather than silently altering historical behaviour.

At small scale, one person may perform several of these roles. In a mature enterprise deployment, plan authoring and production approval should normally be separated.

## One principle across very different users

### Enterprise corporate communications

An enterprise may have tenant administrators, security classifications, separate Power Platform environments and formal approval authorities. Plans may be scoped to a department, document class or SharePoint intake location. A corporate communications team might receive approved plans for:

- annual-report editing;
- sustainability-report normalization;
- website and corporate-profile updates;
- speech preparation;
- published-background consolidation;
- mechanical proofreading before external release.

The organization may approve only particular models, data locations, source repositories and output destinations. Every run must record the exact plan version and policy context.

### An individual writing dive-camp websites

The individual user requires far less organizational machinery, but still benefits from approved plans. Their available plans might cover:

- converting operator notes into consistent destination pages;
- normalizing dive-site descriptions;
- preserving safety and certification statements;
- creating search-friendly web copy;
- checking repeated facts across several camp pages;
- producing a final structured Word or Markdown response.

If the writer requests a new multilingual comparison page, the agent can prepare a custom-plan request for an AutoScribe superuser. Once implemented and tested, that plan may be assigned to the user or, if generally useful, published as a standard product plan.

The individual does not need an internal IT department. AutoScribe supplies the approval authority as part of the service. The enterprise may instead nominate its own trained plan managers, subject to platform policy.

Thus the difference lies primarily in governance ownership:

| Setting | Who requests | Who approves and publishes |
| --- | --- | --- |
| Individual or small business | The user | AutoScribe superuser |
| Managed client project | Project user | AutoScribe or nominated project manager |
| Enterprise | Authorized employee | Enterprise plan authority, AutoScribe authority, or both |

The execution engine still accepts only an approved, immutable plan version.

## Plan scopes

Approved plans should be assignable at several levels:

- **system-wide:** standard AutoScribe plans available to eligible users;
- **organization:** plans approved for one enterprise tenant;
- **project:** plans limited to a named body of work;
- **user:** specialist plans available to one user;
- **trial:** temporary plans with an expiry date and restricted input set.

Availability does not imply permission to process every document. User authorization, document classification, intake location and plan authorization remain independent checks.

## Parameters are not plan editing

Plans should expose bounded parameters where variation is safe. These might include target length, supported audience categories, permitted tone choices or an approved output format.

A parameter must not become a disguised free-form system instruction. Each parameter needs a defined type, permitted range and known effect. Text supplied as manuscript context remains untrusted content; it must not be allowed to override plan rules or introduce new tools.

When the requested variation changes the execution graph, standing instructions, model exposure, writeback policy or verification obligations, it requires a new plan version.

## Immutability, reproducibility and audit

Once published, a plan version should be immutable. Every run should retain:

- the plan identifier and version;
- the permitted parameter values used;
- the applicable instruction versions;
- models, scripts and deterministic components invoked;
- input and response identities;
- approvals and ambiguity resolutions;
- processing and writeback outcomes.

Correcting or improving a plan creates a new version. Existing and completed runs continue to refer to the definition actually used. This is necessary for debugging a dive-camp page just as it is for auditing an annual report; only the consequences and retention requirements differ.

## Security and quality benefits

The approved-workflow rule provides:

- reproducible processing;
- controlled model and data exposure;
- predictable cost envelopes;
- testable instructions and transformations;
- reliable support and debugging;
- reduced prompt-injection opportunities;
- consistent quality expectations;
- auditable approvals and outputs;
- gradual extension without destabilizing existing users.

It also creates a valuable product feedback loop. Repeated custom requests can be evaluated and turned into robust standard plans. AutoScribe’s plan library grows from observed user needs rather than arbitrary feature accumulation.

## Recommended system rule

The execution service should reject any dispatch that does not resolve to an approved plan version available to the user, project and organization. The conversational agent may propose, explain and request workflows, but it should not possess authority to publish or bypass them.

The governing rule should be enforced by the service, not merely expressed in the interface:

> No production run without an authorized plan identifier and immutable version.

## Conclusion

AutoScribe should offer conversational freedom at the request layer and strict control at the execution layer. An enterprise employee and an independent writer serving dive camps should both be able to describe unusual needs in ordinary language. Neither should cause an improvised, untested pipeline to execute merely because an agent understood the request.

The agent translates novelty into a plan request. A qualified human approves and implements the machinery. The user then receives a tested, versioned workflow appropriate to their account and material.

This common protocol gives small users enterprise-grade reliability without enterprise bureaucracy, while giving enterprises the governance required to adopt an external editorial pipeline. It is therefore not a limitation placed on particular customers. It is a defining architectural principle of AutoScribe.
