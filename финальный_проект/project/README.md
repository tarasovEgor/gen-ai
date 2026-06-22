# CloudPay Knowledge Assistant

Ассистент по корпусу внутренних интервью о платёжной платформе CloudPay.
Отвечает на вопросы HR/продакта с проверяемыми цитатами.

**Трек B** — финальный проект курса «Практическое применение генеративного ИИ».

## Техники

1. **Hybrid RAG** — Chroma + keyword grep boost (`hybrid_retrieve`)
2. **Агент с инструментами** — `search_kb`, `grep_corpus`, `get_excerpt`, `list_speakers`
3. **Структурированный вывод** — Pydantic `Answer` + `field_validator`
4. **LLM-as-judge** — groundedness
5. **Мультиагент** — Router → Agent → Judge

## Быстрый старт

```bash
cd финальный_проект/project
cp .env.example .env   # или используйте корневой .env репозитория
uv sync                # из корня gen-ai
uv run python pipeline.py --ingest
uv run python pipeline.py --question "Кто жаловался на задержку webhook?"
uv run python eval.py --retrieval-only   # 18/18 retrieval smoke (~10 с)
uv run python eval.py --force            # полный eval (нужен баланс API)
```

## Структура

```
project/
├── pipeline.py      # главная команда
├── eval.py          # eval ≥18 вопросов
├── schema.py        # Pydantic + validators
├── rag.py           # индекс Chroma
├── agent.py         # ReAct-агент
├── router.py        # классификация вопроса
├── judge.py         # LLM-as-judge
├── hallucination.py # ghost-цитаты
├── input/
│   ├── corpus/      # 10 интервью (.txt)
│   └── gold.json    # 18 тестовых вопросов
└── output/          # eval_results.json, eval_retrieval_only.json, trace.jsonl
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `LLM_BASE_URL` | OpenAI-совместимый endpoint |
| `LLM_AUTH_TOKEN` | API-ключ |
| `LLM_MODEL` | Имя модели |

## Артефакты

- `output/last_result.json` — последний ответ + trace + path metrics
- `output/eval_results.json` — таблица eval (правильность + путь)
- `chroma_db/` — локальный индекс (создаётся `--ingest`)
