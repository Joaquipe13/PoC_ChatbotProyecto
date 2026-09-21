"""Evaluación conversacional del chatbot (Fase 12): un simulador conversa con el
sistema, las conversaciones quedan registradas y se analizan. Ver evals/README.md.

Todo esto usa el LLM real del orquestador (red y cuota): no corre con `pytest` ni
en CI (`testpaths = ["tests"]`). Los tests de las piezas puras están en
`evals/test_invariantes.py` y se corren a propósito: `uv run pytest evals`.
"""
