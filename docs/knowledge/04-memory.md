---
name: justllama-agent-memory
description: justLLAMA's agent memory system — short-term conversation memory, long-term SQLite-backed persistent memory, retrieval/injection, and the unified MemoryManager API.
tags: [memory, short-term, long-term, sqlite, context, persistence]
audience: llm
---

# justLLAMA — Agent Memory

Agent memory gives conversations continuity beyond a single session. It is
**optional and disabled by default** (`memory/enabled = false`) and is
orchestrated by `MemoryManager` (`memory/manager.py`, exposed as
`memoryManager`), which composes two stores.

## Short-term memory (`memory/short_term.py`, `ShortTermMemory`)

- An in-RAM rolling window of recent messages backed by a bounded deque.
- Capacity is `memory/max_short_term` (default **50** messages); older messages
  fall off as new ones arrive.
- Holds the working conversation context. Cleared on `clear_short_term()`.
- Accepts role/content pairs (`add_message`) or raw message dicts
  (`add_raw_message`), and can format itself for prompt injection.

## Long-term memory (`memory/long_term.py`, `LongTermMemory`)

- **SQLite-backed** persistent store; default path
  `~/.local/share/justllama/memory.db` (can be `:memory:` for ephemeral).
- Supports full-text search over stored memories, categories, listing,
  per-id deletion (`forget`), and a total count.
- Each memory has content and a `category` (default `"general"`).
- Closed cleanly on app shutdown (`long_term.close()`).

## Unified API (`MemoryManager`)

The manager is what QML and the chat flow talk to. Its intended per-turn cycle:

1. Retrieve relevant long-term memories via FTS search (`retrieve_context`).
2. Include short-term history as real chat messages (`get_short_term_history`).
3. Augment the system prompt with long-term context only
   (`get_system_prompt_addition` → "Relevant memories"). Short-term history is
   deliberately excluded here to avoid duplicating the conversation, since the
   caller already sends it as real messages.
4. After the response, optionally store new memories (`store_memory`).

Key slots (all no-op / return empty when memory is disabled where noted):

| Slot | Purpose |
|------|---------|
| `set_enabled(bool)` / `is_enabled()` | Toggle/query the feature. |
| `add_message(role, content)` / `add_raw_message(dict)` | Append to short-term. |
| `get_short_term_history(limit)` | Short-term history as JSON. |
| `retrieve_context(query, limit=5)` | Long-term FTS search (empty if disabled). |
| `get_system_prompt_addition()` | Build the prompt context block. |
| `store_memory(content, category)` | Persist a long-term memory (id returned; empty if disabled). |
| `list_all_memories()` / `list_memories_by_category(cat)` | Browse. |
| `forget_memory(id)` | Delete one memory (True if removed). |
| `clear_short_term()` / `clear_long_term()` / `clear_all()` | Wipe. |
| `stats()` | `{short_term_count, long_term_count, enabled}`. |

A dedicated **Memory view** in the UI lets the user browse and manage both
stores.

## Relationship to RAG and context compaction

- Memory and RAG are **independent** subsystems: RAG grounds answers in
  documents, memory carries conversational/user facts across turns/sessions.
  Both inject text into the prompt and both consume the finite context window.
- justLLAMA also supports **context compaction** — summarizing and compacting
  long conversations to stay within the model's context limit.

## Guidance for an operating model

- Treat long-term memory as **user-owned personal data**. Store only what is
  useful and non-sensitive; never persist secrets/API keys.
- Retrieved memories are hints about prior context, not authoritative facts;
  reconcile them with the current conversation.
- When memory is disabled, retrieval/store calls return empty — do not assume
  persistence is happening.
