from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, Dialect
from sqlalchemy.types import TypeDecorator


class PydanticJSON(TypeDecorator[BaseModel]):
    """Columna JSON respaldada por un modelo pydantic.

    Guardar las specs como texto suelto invita a que cada punto del codigo
    invente su propia forma de leerlas. Con esto, lo que sale de la base de
    datos ya viene validado y tipado.

    Hoy `JSON` sobre SQLite; el dia que haya Postgres se cambia `impl` por
    `JSONB` y nada mas se entera.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, model: type[BaseModel], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model = model

    def process_bind_param(self, value: BaseModel | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return value.model_dump(mode="json", by_alias=True)

    def process_result_value(self, value: Any, dialect: Dialect) -> BaseModel | None:
        if value is None:
            return None
        return self._model.model_validate(value)
