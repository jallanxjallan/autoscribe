---
date: 2026-08-05
title: AutoScribe Design Note - Adhoc Directives and Conditional
  Execution
type: design-note
---

# Summary

During discussion, a broader architectural pattern emerged from the
existing adhoc directive mechanism.

## Original purpose

Adhoc directives are prepended to content immediately before dispatch.
This allows the editor to issue one-off instructions without creating or
maintaining a dedicated instruction file.

This keeps temporary editorial intent close to the content and avoids
unnecessary configuration.

## New role: conditional execution

The same mechanism can also control pipeline execution.

Instead of every plan step always invoking an LLM, the engine should
inspect the current directive immediately before executing each step.

Possible outcomes are:

-   run
-   run with modified behaviour
-   skip

When skipped, the engine records an explicit runtime result but does not
make an LLM call.

## Mid-chain directives

Directives are not limited to dispatch-time author input.

Local scripts can generate directives during execution.

Example:

1.  A local detector searches for AI filler patterns.
2.  If patterns are found, it emits findings for the correction step.
3.  If no patterns are found, it emits a skip directive.
4.  The engine skips the expensive correction model entirely.

This allows inexpensive deterministic processing to gate expensive model
calls.

## Architectural principle

Every pipeline step may produce both:

-   transformed content
-   control directives for later steps

This removes the need for a separate conditional workflow language while
keeping plans deterministic.

## Benefits

-   Fewer unnecessary LLM calls.
-   Lower token costs.
-   Reduced latency.
-   Simpler plans.
-   Transparent execution history.
-   Easy inspection because directives travel with the content.

## Design philosophy

The idea originated from simplifying the editor experience rather than
designing a workflow engine.

Instead of creating temporary instruction records, the editor simply
writes an adhoc directive into the content being processed.

The same mechanism naturally evolved into a general-purpose runtime
control channel, allowing deterministic local scripts to decide whether
later expensive AI steps should run.
