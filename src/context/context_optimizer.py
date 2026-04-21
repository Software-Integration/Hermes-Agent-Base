from dataclasses import dataclass
from typing import List


@dataclass
class OptimizedContext:
    compact_messages: List[dict]
    summary: str


def _simple_summary(messages: List[dict], max_words: int = 220) -> str:
    words = []
    for msg in messages:
        words.extend(str(msg.get("content", "")).split())
        if len(words) >= max_words:
            break
    if not words:
        return ""
    clipped = words[:max_words]
    clipped.append("...")
    return " ".join(clipped)


def _semantic_system_messages(retrieved_contexts: List[str]) -> List[dict]:
    recall_lines = [f"- {item}" for item in retrieved_contexts[:3] if item]
    if not recall_lines:
        return []
    return [{"role": "system", "content": "[semantic_recall]\n" + "\n".join(recall_lines)}]


def optimize_context(
    tenant_id: str,
    incoming_messages: List[dict],
    mem_history: List[dict],
    retrieved_contexts: List[str],
    char_limit: int,
    max_turns: int,
    max_summary_words: int,
) -> OptimizedContext:
    combined = list(mem_history) + list(incoming_messages)
    full_text = "".join(str(m.get("content", "")) for m in combined)
    prefix_messages = _semantic_system_messages(retrieved_contexts)

    if len(full_text) <= char_limit and len(combined) <= max_turns * 2:
        return OptimizedContext(compact_messages=prefix_messages + combined, summary="")

    tail = combined[-max_turns * 2 :]
    head = combined[: max(0, len(combined) - len(tail))]
    summary = _simple_summary(head, max_words=max_summary_words)
    compact = list(prefix_messages)
    if summary:
        compact.append({"role": "system", "content": f"[context_summary]{summary}"})
    compact.extend(tail)
    return OptimizedContext(compact_messages=compact, summary=summary)
