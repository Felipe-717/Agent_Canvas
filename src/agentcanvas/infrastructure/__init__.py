"""Adaptadores: implementaciones concretas de los puertos de `application`.

Es la unica capa que conoce OpenAI, SQLAlchemy, FastAPI, pandas o el sistema
de archivos. Nadie importa desde aqui salvo `bootstrap`.
"""
