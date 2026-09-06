from dataclasses import dataclass

from asc.control.repository import ControlRepository, GitInstruction
from asc import extensions
from asc.models.control.plan import Plan


@dataclass(frozen=True, slots=True)
class LoadedPlan:
    """Current immutable plan version read directly from Control Git."""

    slug: str
    revision: str
    path: str
    plan: Plan
    instructions: dict[str, GitInstruction]

    @property
    def source_ref(self) -> str:
        return f"control-git@{self.revision}:{self.path}"

    @property
    def plan_key(self) -> str:
        """Git source reference retained in the enqueue report contract."""
        return self.source_ref

    @property
    def step_count(self) -> int:
        return self.plan.total_steps


def load_plan(plan_slug: str) -> LoadedPlan:
    control = ControlRepository()
    source = control.read_plan(plan_slug)
    instructions = resolve_components(source.plan, control)
    return LoadedPlan(
        slug=plan_slug,
        revision=control.revision,
        path=source.path,
        plan=source.plan,
        instructions=instructions,
    )


def resolve_components(
    plan: Plan, control: ControlRepository
) -> dict[str, GitInstruction]:
    """Resolve only selected dependencies before any runtime state is written."""
    instructions = {}
    for step in plan.steps.values():
        engine = step["engine"]
        _component(plan, "engines", "engine", engine, control.revision)
        for field, registry, label in (
            ("model", "models", "model"),
            ("script", "local_scripts", "local script"),
            ("rag_profile", "rag_profiles", "RAG profile"),
        ):
            if field in step:
                metadata = _component(
                    plan, registry, label, step[field], control.revision
                )
                if field == "script":
                    _execution_file("scripts", step[field], label)
                elif field == "rag_profile":
                    path = extensions.EXTENSIONS_ROOT / metadata["path"]
                    if not path.is_file():
                        raise FileNotFoundError(
                            f"missing RAG profile: {step[field]} ({path})"
                        )
        if step["engine_kind"] != "script":
            _execution_file("engines", engine, "engine")
        for identities in step["instructions"].values():
            for identity in identities:
                if identity not in instructions:
                    instructions[identity] = control.read_instruction(identity)
    return instructions


def _component(plan: Plan, registry: str, label: str, name: str, revision: str):
    try:
        return plan.capabilities[registry][name]
    except KeyError:
        raise KeyError(
            f"missing {label}: {name} at Control revision {revision}"
        ) from None


def _execution_file(category: str, name: str, label: str) -> None:
    try:
        extensions._resolve_path(category, name)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"missing {label}: {name} (execution artifact unavailable)"
        ) from exc


__all__ = ["LoadedPlan", "load_plan", "resolve_components"]
