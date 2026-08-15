"""De una frase del usuario a un grafico listo para pintar.

Junta las tres piezas: el agente propone la spec, el dominio la valida contra
el schema, y el motor determinista la ejecuta. Lo que se devuelve incluye la
spec, porque es lo que hay que guardar: los datos se pueden recalcular, la
intencion no.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agentcanvas.agent.trace import AgentTrace
from agentcanvas.agent.visual_agent import VisualSpecAgent
from agentcanvas.application.ports.query import DatasetSamplerPort, QueryEnginePort
from agentcanvas.application.ports.repositories import DatasetRepositoryPort
from agentcanvas.application.ports.storage import FileStoragePort
from agentcanvas.application.use_cases.render_visual import DatasetHasNoDataError
from agentcanvas.domain.shared.errors import NotFoundError
from agentcanvas.domain.visual.result import VisualData
from agentcanvas.domain.visual.spec import VisualSpec

SAMPLE_ROWS = 8


class CreateVisualCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner_id: str
    dataset_id: str
    instruction: str


class CreateVisualResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    spec: VisualSpec
    data: VisualData
    trace: AgentTrace


class CreateVisualUseCase:
    def __init__(
        self,
        *,
        datasets: DatasetRepositoryPort,
        storage: FileStoragePort,
        engine: QueryEnginePort,
        sampler: DatasetSamplerPort,
        agent: VisualSpecAgent,
    ) -> None:
        self._datasets = datasets
        self._storage = storage
        self._engine = engine
        self._sampler = sampler
        self._agent = agent

    async def execute(self, command: CreateVisualCommand) -> CreateVisualResult:
        dataset = await self._datasets.get(command.dataset_id)
        if dataset is None or dataset.owner_id != command.owner_id:
            raise NotFoundError("dataset", command.dataset_id)
        if dataset.current_version_id is None:
            raise DatasetHasNoDataError(dataset.name)
        version = await self._datasets.get_version(dataset.current_version_id)
        if version is None:
            raise NotFoundError("version de dataset", dataset.current_version_id)

        source = self._storage.path_for(version.storage_key)
        proposal = await self._agent.propose(
            instruction=command.instruction,
            dataset_name=dataset.name,
            schema=dataset.schema_,
            sample=self._sampler.sample(source, rows=SAMPLE_ROWS),
        )

        # La spec ya paso la validacion dentro del agente; ejecutarla aqui no
        # puede fallar por culpa del modelo.
        data = self._engine.execute(proposal.value, source=source, schema=dataset.schema_)
        return CreateVisualResult(spec=proposal.value, data=data, trace=proposal.trace)
