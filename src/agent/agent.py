"""ReAct agent: tool-calling loop over the indexed repo, with a hard iteration cap."""

import uuid
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError

import config
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools.list_files import list_files
from src.agent.tools.read_file import read_file
from src.agent.tools.semantic_search import semantic_search
from src.agent.tools.why_does_this_exist import why_does_this_exist
from src.utils.citations import Citation, dedupe
from src.utils.logger import get_logger

logger = get_logger(__name__)

_agent = None

# create_agent's tool loop counts each model turn and each tool turn as one
# graph step; MAX_ITERATIONS tool-call rounds need 2 steps each, plus one
# final model turn to produce the answer.
_RECURSION_LIMIT = config.MAX_ITERATIONS * 2 + 1


@dataclass(frozen=True)
class AskResult:
    answer: str
    citations: list[Citation]


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            model=f"openai:{config.LLM_MODEL}",
            tools=[read_file, list_files, semantic_search, why_does_this_exist],
            system_prompt=SYSTEM_PROMPT,
            checkpointer=MemorySaver(),
        )
    return _agent


def ask(question: str) -> AskResult:
    """Run the agent on `question`, returning its final answer plus every citation \
    the tools it called actually returned.

    Enforces config.MAX_ITERATIONS. On exhaustion, returns whatever answer
    text and citations the agent had produced so far plus a note — the agent
    never loops indefinitely.
    """
    agent = _get_agent()
    run_config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "recursion_limit": _RECURSION_LIMIT,
    }

    try:
        result = agent.invoke({"messages": [{"role": "user", "content": question}]}, config=run_config)
        messages = result["messages"]
        return AskResult(answer=_last_answer(messages), citations=_collect_citations(messages))
    except GraphRecursionError:
        logger.warning(f"agent hit max_iterations={config.MAX_ITERATIONS} for question: {question!r}")
        messages = agent.get_state(run_config).values["messages"]
        answer = _last_answer(messages)
        note = f"Stopped after {config.MAX_ITERATIONS} steps. Here's what I found so far."
        return AskResult(
            answer=f"{answer}\n\n({note})" if answer else note,
            citations=_collect_citations(messages),
        )


def _last_answer(messages: list) -> str:
    """The most recent AI-authored message with real text content.

    Must filter to AIMessage specifically, not just "any message with a
    non-empty string content" — a ToolMessage's content is a string too (a
    read_file call's entire file text, in one real case), and on the
    recursion-limit fallback path the last message in state can be a
    ToolMessage whose result the model never got to respond to. Checking
    type, not just truthiness, is what keeps a raw tool dump from being
    returned as if it were the agent's answer.
    """
    for message in reversed(messages):
        if isinstance(message, AIMessage) and isinstance(message.content, str) and message.content.strip():
            return message.content
    return ""


def _collect_citations(messages: list) -> list[Citation]:
    """Every citation attached to a tool call this run made, deduplicated.

    Pulled from each ToolMessage's `artifact` — the structured data a tool
    returned alongside its LLM-facing text (`response_format="content_and_artifact"`)
    — never parsed from the model's own prose, so a citation's file/line
    numbers are exactly what the tool retrieved, not a retyped copy of it.

    On the recursion-limit fallback path, messages come from the
    checkpointer's persisted state rather than a live `invoke()` return, and
    round-trip through it as plain dicts instead of `Citation` instances —
    normalize both shapes.
    """
    citations: list[Citation] = []
    for message in messages:
        if isinstance(message, ToolMessage) and message.artifact:
            for item in message.artifact:
                citations.append(item if isinstance(item, Citation) else Citation(**item))
    return dedupe(citations)
