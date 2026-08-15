"""El harness: presupuesto, ciclo de correccion y traza.

Todo contra `FakeLLM`. Estos tests son los que permiten tocar prompts sin miedo:
si un cambio rompe el contrato del agente, se ve aqui y no en la factura.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from agentcanvas.agent.budget import Budget, BudgetExceededError, BudgetTracker
from agentcanvas.agent.structured import (
    AgentFailedError,
    StructuredGenerator,
    StructuredResult,
    Validator,
)
from agentcanvas.agent.trace import StepKind
from agentcanvas.application.ports.llm import LLMUnavailableError, Role, Usage
from tests.fakes import FakeLLM, json_response, malformed_response


class Answer(BaseModel):
    total: int = Field(ge=0)
    label: str


async def _generate(
    llm: FakeLLM,
    *,
    budget: Budget | None = None,
    validate: Validator | None = None,
) -> StructuredResult[Answer]:
    generator = StructuredGenerator(llm, budget)
    return await generator.generate(
        output=Answer,
        name="answer",
        system="Eres util",
        user="Dame la respuesta",
        validate=validate,
    )


# ------------------------------------------------------------------ presupuesto


def test_the_tracker_counts_iterations_and_stops() -> None:
    tracker = BudgetTracker(Budget(max_iterations=2))

    assert tracker.start_iteration() == 1
    assert tracker.start_iteration() == 2
    with pytest.raises(BudgetExceededError) as error:
        tracker.start_iteration()

    assert error.value.limit == "iteraciones"


def test_the_tracker_accumulates_tokens_and_stops() -> None:
    tracker = BudgetTracker(Budget(max_iterations=10, max_tokens=100))

    tracker.record(Usage(input_tokens=60, output_tokens=20))
    with pytest.raises(BudgetExceededError) as error:
        tracker.record(Usage(input_tokens=30))

    assert error.value.limit == "tokens"
    assert error.value.spent == 110


def test_without_a_token_limit_only_iterations_matter() -> None:
    tracker = BudgetTracker(Budget(max_iterations=3))
    tracker.record(Usage(input_tokens=1_000_000))
    assert tracker.iterations == 0


# ------------------------------------------------------------------- generacion


async def test_a_valid_answer_at_the_first_try() -> None:
    llm = FakeLLM([json_response({"total": 5, "label": "ok"}, input_tokens=12, output_tokens=4)])

    result = await _generate(llm)

    assert result.value == Answer(total=5, label="ok")
    assert llm.calls == 1
    assert result.trace.iterations == 2
    assert result.trace.usage.total_tokens == 16


async def test_a_schema_violation_is_returned_to_the_model_and_corrected() -> None:
    llm = FakeLLM(
        [
            json_response({"total": -1, "label": "mal"}),
            json_response({"total": 7, "label": "bien"}),
        ]
    )

    result = await _generate(llm)

    assert result.value.total == 7
    assert llm.calls == 2
    assert result.trace.repairs == 1


async def test_the_correction_message_names_the_offending_field() -> None:
    llm = FakeLLM(
        [
            json_response({"total": -1, "label": "mal"}),
            json_response({"total": 1, "label": "bien"}),
        ]
    )

    await _generate(llm)

    repair = llm.requests[1].messages[-1]
    assert repair.role is Role.USER
    # Sin el nombre del campo, el modelo solo puede adivinar que corregir.
    assert "total" in repair.content


async def test_domain_problems_are_returned_verbatim() -> None:
    llm = FakeLLM(
        [
            json_response({"total": 1, "label": "x"}),
            json_response({"total": 1, "label": "ventas"}),
        ]
    )

    def validate(answer: Answer) -> tuple[str, ...]:
        return () if len(answer.label) > 3 else ("La etiqueta 'x' es demasiado corta",)

    await _generate(llm, validate=validate)

    assert "La etiqueta 'x' es demasiado corta" in llm.requests[1].messages[-1].content


async def test_the_previous_attempt_stays_in_the_conversation() -> None:
    llm = FakeLLM(
        [json_response({"total": -1, "label": "mal"}), json_response({"total": 1, "label": "ok"})]
    )

    await _generate(llm)

    # El modelo necesita ver lo que propuso para poder corregirlo.
    assert llm.requests[1].messages[-2].role is Role.ASSISTANT
    assert "-1" in llm.requests[1].messages[-2].content


async def test_a_response_without_json_is_treated_as_a_correctable_problem() -> None:
    llm = FakeLLM([malformed_response("No puedo"), json_response({"total": 1, "label": "ok"})])

    result = await _generate(llm)

    assert result.value.total == 1
    assert "JSON" in llm.requests[1].messages[-1].content


async def test_it_gives_up_within_the_budget_and_reports_the_last_problems() -> None:
    llm = FakeLLM([json_response({"total": -1, "label": "mal"}) for _ in range(3)])

    with pytest.raises(AgentFailedError) as error:
        await _generate(llm, budget=Budget(max_iterations=3))

    assert llm.calls == 3
    assert any("total" in problem for problem in error.value.problems)
    assert error.value.trace.steps[-1].kind is StepKind.FAILED


async def test_the_token_budget_also_stops_it() -> None:
    llm = FakeLLM(
        [
            json_response({"total": -1, "label": "mal"}, input_tokens=90, output_tokens=20),
            json_response({"total": 1, "label": "ok"}),
        ]
    )

    with pytest.raises(AgentFailedError):
        await _generate(llm, budget=Budget(max_iterations=5, max_tokens=100))


async def test_a_provider_failure_is_not_swallowed() -> None:
    # Que el proveedor este caido no es un error del modelo: reintentar
    # pidiendole que se corrija no arregla nada y gasta el presupuesto.
    llm = FakeLLM([LLMUnavailableError("502")])

    with pytest.raises(LLMUnavailableError):
        await _generate(llm)


async def test_the_trace_records_every_attempt() -> None:
    llm = FakeLLM(
        [json_response({"total": -1, "label": "mal"}), json_response({"total": 1, "label": "ok"})]
    )

    result = await _generate(llm)

    kinds = [step.kind for step in result.trace.steps]
    assert kinds == [
        StepKind.PROPOSAL,
        StepKind.REJECTED,
        StepKind.PROPOSAL,
        StepKind.ACCEPTED,
    ]


async def test_the_json_schema_of_the_output_travels_in_the_request() -> None:
    llm = FakeLLM([json_response({"total": 1, "label": "ok"})])

    await _generate(llm)

    response_format = llm.requests[0].response_format
    assert response_format is not None
    assert response_format.name == "answer"
    assert "total" in response_format.schema_["properties"]

