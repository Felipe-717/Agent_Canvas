"""Extraer JSON de lo que devuelve un modelo que no tiene salidas estructuradas."""

from __future__ import annotations

import pytest

from agentcanvas.application.ports.llm import LLMProtocolError
from agentcanvas.infrastructure.llm.parsing import extract_json_object


def test_plain_json() -> None:
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_json_inside_a_code_fence() -> None:
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_inside_an_unlabelled_fence() -> None:
    assert extract_json_object('```\n{"a": 1}\n```') == {"a": 1}


def test_json_surrounded_by_chatter() -> None:
    text = 'Claro, aqui tienes:\n{"tipo": "bar"}\nEspero que te sirva.'
    assert extract_json_object(text) == {"tipo": "bar"}


def test_nested_objects_are_not_cut_short() -> None:
    text = 'x {"a": {"b": {"c": 1}}, "d": 2} y'
    assert extract_json_object(text) == {"a": {"b": {"c": 1}}, "d": 2}


def test_braces_inside_strings_do_not_confuse_the_scanner() -> None:
    text = '{"titulo": "Ventas {Norte}", "n": 1}'
    assert extract_json_object(text) == {"titulo": "Ventas {Norte}", "n": 1}


def test_escaped_quotes_are_respected() -> None:
    text = '{"titulo": "dijo \\"hola\\"", "n": 1}'
    assert extract_json_object(text) == {"titulo": 'dijo "hola"', "n": 1}


def test_text_without_json_fails_clearly() -> None:
    with pytest.raises(LLMProtocolError):
        extract_json_object("No puedo ayudarte con eso")


def test_an_unclosed_object_fails() -> None:
    with pytest.raises(LLMProtocolError):
        extract_json_object('{"a": 1')


def test_a_json_array_is_not_an_object() -> None:
    with pytest.raises(LLMProtocolError):
        extract_json_object("[1, 2, 3]")
