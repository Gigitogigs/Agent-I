# Retrieval Agent

The Retrieval Agent is a specialized subagent within the multi-agent customer support system. Its primary responsibility is to fetch relevant information from the knowledge base (vector database) to answer user queries accurately and without hallucination.

## Architecture

The Retrieval Agent is implemented as a LangGraph state machine with the following three core nodes:

1. **`rewrite_query_node`**:
   Transforms the raw user query into structured search representations optimized for vector retrieval. It uses an LLM to generate:
   - A **declarative statement** that captures the core intent.
   - A **hypothetical answer** (HyDE - Hypothetical Document Embeddings) to improve semantic matching.
   - A list of **keywords** for potential hybrid search use.
   This node also takes the chat history into account for context (e.g., pronoun resolution).

2. **`vector_search_node`**:
   Executes a similarity search against the `pgvector` database. It combines the declarative query and hypothetical answer to query the vector store and retrieve the most relevant document chunks.

3. **`generate_answer_node`**:
   Synthesizes a final, grounded answer to the user's query based *strictly* on the retrieved document chunks. The answer includes citations to the specific source chunk IDs used. If the retrieved documents do not contain sufficient information, the model is instructed to indicate insufficient coverage rather than hallucinating an answer.

## Tool Integration

The agent exposes the `invoke_retrieval_agent` function, which is decorated as a `@tool`. This allows the root orchestrator agent (or other subagents) to delegate retrieval tasks to this agent seamlessly.

### Inputs (`RetrievalRequest`)
- `query` (str): The search query or question.
- `context_slice` (list[str]): Relevant context or conversation history.
- `top_k` (int, optional): The number of relevant documents to retrieve. Defaults to 5.
- `filters` (dict, optional): Metadata filters to apply during the vector search.

### Outputs (`RetrievalResult`)
Returns a structured result containing:
- The generated answer string.
- A list of source chunks referenced in the answer to provide traceability.

## Configuration

The underlying LLM provider and model for the Retrieval Agent are configured in the global `subagent_registry.yaml` file under the `retrieval_agent` key. The agent dynamically loads this configuration using `harness.model_factory.build_model`.
