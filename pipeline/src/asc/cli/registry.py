from __future__ import annotations

import json
from typing import Annotated

import typer

from asc.registries.catalog import (
    catalog_path,
    remove_registered_component,
    upsert_registered_component,
)
from asc.registries.contracts import (
    ContractResolutionError,
    available_contracts,
    contract_for_ref,
    format_contract_text,
)
from asc.registries.extensions import DEFAULT_TRANSFORM, load_engine_call, load_transform
from asc.registries.snapshot import ENGINE_STEP_FIELDS, build_registry_snapshot

app = typer.Typer(no_args_is_help=True, help="Inspect and register runtime components.")
contract_app = typer.Typer(no_args_is_help=True, help="Inspect model input/export contracts.")
app.add_typer(contract_app, name="contract")

REGISTRY_CHOICES = {"engines", "local_scripts", "rag_profiles"}
ENGINE_KIND_CHOICES = set(ENGINE_STEP_FIELDS)


def _echo_json(value: object) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True))


def _component_label(component: str) -> str:
    module_name = component.split(":", 1)[0]
    return module_name.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").title()


def _split_script_pointer(component: str, callable_name: str) -> tuple[str, str, str]:
    module_name, sep, inline_callable = component.strip().partition(":")
    selected_callable = inline_callable if sep else callable_name
    key = component.strip() if sep else module_name
    return module_name, selected_callable, key


@app.command("snapshot")
def snapshot() -> None:
    """Emit the immutable runtime registry snapshot as JSON."""
    _echo_json(build_registry_snapshot())


@app.command("list")
def list_components(
    registry: Annotated[
        str,
        typer.Argument(help="One of: all, engines, local_scripts, rag_profiles."),
    ] = "all",
    *,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of tab-separated rows."),
    ] = False,
) -> None:
    """List registered/discovered components."""
    snapshot_data = build_registry_snapshot()
    registries = snapshot_data["registries"]

    if registry == "all":
        selected = registries
    elif registry in REGISTRY_CHOICES:
        selected = {registry: registries.get(registry, {})}
    else:
        allowed = ", ".join(["all", *sorted(REGISTRY_CHOICES)])
        raise typer.BadParameter(f"registry must be one of: {allowed}")

    if json_output:
        _echo_json(selected)
        return

    for registry_name, records in selected.items():
        for key, record in records.items():
            label = record.get("label", "")
            kind = record.get("kind", record.get("callable", ""))
            typer.echo(f"{registry_name}\t{key}\t{kind}\t{label}")


@app.command("register-engine")
def register_engine(
    component: Annotated[
        str,
        typer.Argument(help="Engine module import name, for example autoscribe_engines.openai."),
    ],
    *,
    label: Annotated[str | None, typer.Option("--label", help="Display label.")] = None,
    kind: Annotated[
        str,
        typer.Option("--kind", help="Engine kind: llm, local, or rag."),
    ] = "llm",
    step_field: Annotated[
        list[str] | None,
        typer.Option("--step-field", help="Allowed/expected job-step field. Repeatable."),
    ] = None,
    no_check: Annotated[
        bool,
        typer.Option("--no-check", help="Register without importing or validating make_call."),
    ] = False,
) -> None:
    """Register an engine component by import name."""
    if kind not in ENGINE_KIND_CHOICES:
        allowed = ", ".join(sorted(ENGINE_KIND_CHOICES))
        raise typer.BadParameter(f"engine kind must be one of: {allowed}")

    if not no_check:
        load_engine_call(component)

    record = {
        "key": component,
        "label": label or _component_label(component),
        "kind": kind,
        "module": component,
        "step_fields": list(step_field or ENGINE_STEP_FIELDS[kind]),
    }
    path = upsert_registered_component(registry="engines", key=component, record=record)
    typer.echo(f"registered engine: {component}")
    typer.echo(f"catalog: {path}")


@app.command("register-script")
def register_script(
    component: Annotated[
        str,
        typer.Argument(
            help="Script module import name, optionally module:callable for non-transform callables."
        ),
    ],
    *,
    label: Annotated[str | None, typer.Option("--label", help="Display label.")] = None,
    callable_name: Annotated[
        str,
        typer.Option("--callable", help="Callable name when component does not include ':'."),
    ] = DEFAULT_TRANSFORM,
    no_check: Annotated[
        bool,
        typer.Option("--no-check", help="Register without importing or validating the callable."),
    ] = False,
) -> None:
    """Register a local script transform by import name."""
    module_name, selected_callable, key = _split_script_pointer(component, callable_name)
    pointer = f"{module_name}:{selected_callable}"

    if not no_check:
        load_transform(pointer)

    record = {
        "key": key,
        "label": label or _component_label(module_name),
        "module": module_name,
        "callable": selected_callable,
    }
    path = upsert_registered_component(registry="local_scripts", key=key, record=record)
    typer.echo(f"registered local script: {key}")
    typer.echo(f"catalog: {path}")


@app.command("register-rag-profile")
def register_rag_profile(
    key: Annotated[str, typer.Argument(help="RAG profile key or slug.")],
    *,
    label: Annotated[str | None, typer.Option("--label", help="Display label.")] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Optional profile/component reference."),
    ] = None,
) -> None:
    """Register a RAG profile reference without inventing a runtime RAG contract yet."""
    record = {
        "key": key,
        "label": label or _component_label(key),
    }
    if profile:
        record["profile"] = profile

    path = upsert_registered_component(registry="rag_profiles", key=key, record=record)
    typer.echo(f"registered RAG profile: {key}")
    typer.echo(f"catalog: {path}")


@app.command("unregister")
def unregister(
    registry: Annotated[str, typer.Argument(help="engines, local_scripts, or rag_profiles.")],
    key: Annotated[str, typer.Argument(help="Component key to remove from the manual catalog.")],
) -> None:
    """Remove a component from the manual catalog."""
    if registry not in REGISTRY_CHOICES:
        allowed = ", ".join(sorted(REGISTRY_CHOICES))
        raise typer.BadParameter(f"registry must be one of: {allowed}")

    existed = remove_registered_component(registry=registry, key=key)
    if existed:
        typer.echo(f"unregistered {registry}: {key}")
    else:
        typer.echo(f"not found in manual catalog: {registry} {key}")
        typer.echo(f"catalog: {catalog_path()}")


@contract_app.command("list")
def list_contracts(
    *,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of tab-separated rows."),
    ] = False,
) -> None:
    """List registered input/export contract aliases."""
    contracts = available_contracts()

    if json_output:
        _echo_json(contracts)
        return

    for key, record in contracts.items():
        purpose = record.get("purpose", "")
        typer.echo(f"{key}\t{purpose}")


@contract_app.command("show")
def show_contract(
    model: Annotated[
        str,
        typer.Argument(
            help="Contract alias such as input:prompt, export:extracted-result, or a direct model import path."
        ),
    ],
    *,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON instead of human-readable text."),
    ] = False,
) -> None:
    """Dump the live contract for a Pydantic model."""
    try:
        contract = contract_for_ref(model)
    except ContractResolutionError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_output:
        _echo_json(contract)
        return

    typer.echo(format_contract_text(contract))


__all__ = ["app"]
