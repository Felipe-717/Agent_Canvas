"""Harness propio del agente.

Sustituye a un framework tipo LangChain: bucle de agente con estado explicito,
registro de herramientas tipadas, presupuesto (iteraciones / tokens / timeout),
politica de reintentos y traza persistible de cada paso.

Habla con el modelo unicamente a traves de `application.ports.LLMPort`, de modo
que el harness no sabe si detras hay OpenAI o vLLM.
"""
