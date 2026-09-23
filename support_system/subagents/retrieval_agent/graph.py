# subagents/retrieval_agent/graph.py
#
# LangGraph graph definition for the FAQ / RAG (Retrieval-Augmented Generation) Agent.
#
# Responsibility:
#   Answers knowledge and policy questions by retrieving relevant chunks from
#   the knowledge base (KB) stored in pgvector, then grounding the answer in
#   those retrieved chunks. This is the READ-ONLY knowledge subagent — it never
#   executes actions or mutates any state.
#
# Stateless by design:
#   Receives only the query and any orchestrator-provided context for this
#   invocation. All retrieval goes through pgvector_client; no session state
#   is stored here.
#
# Node layout (high-level):
#   1. rewrite_query    — optionally rephrase the user's question into an
#                         embedding-friendly form (e.g. expand acronyms,
#                         resolve pronouns using the provided context slice)
#   2. embed_query      — call the EmbeddingProvider to produce a query vector
#   3. vector_search    — call pgvector_client.similarity_search() for top-k chunks;
#                         if similarity score is below threshold, fall back to
#                         keyword search (hybrid retrieval)
#   4. rerank           — optionally re-rank retrieved chunks by relevance before
#                         passing to the LLM (cross-encoder or reciprocal rank fusion)
#   5. generate_answer  — produce a grounded answer citing the chunk IDs; if
#                         retrieval confidence is too low, return an
#                         "insufficient KB coverage" signal so the Orchestrator
#                         can escalate or ask a clarifying question
#
# Parallelism:
#   This agent is always safe to run in parallel with other read-only calls
#   (e.g. an order lookup) within the same turn.
#
# Memory permissions:
#   Reads from Vector Store only. No write access to any store.

from langchain_core import retrievers
from pydantic import BaseModel, Field
from typing import Annotated, List, Dict, Any, Optional, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.tools import tool

from support_system.harness.model_factory import build_model, load_config

from support_system.rag import pgvector_client
from .schema import RetrievalRequest, RetrievalResult, ChunkRef

class searchQueries(BaseModel):
    declarative_query: str = Field(
        description="Core intent converted into a concise declarative statement (removes conversational filter)."
    )
    hypothetical_answer: str = Field(
        description="A short hypothetical answer (HyDE pattern) that likely matches document chunk embeddings."
    )
    keywords: List[str] = Field(
        description="Key domain-specific terminology and synonyms to ensure semantic overlap."
    )

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    top_k: int
    filters: dict | None
    retrieved_docs: List[Document]
    final_response: RetrievalResult
    rewritten_query: searchQueries


rewrite_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert search-query optimizer for a customer-support knowledge base.
    Your sole job is to transform an incoming customer question into three complementary search
    representations that maximise recall when run against a cosine-similarity vector index.

    You will output a JSON object with exactly three fields:

    1. "declarative_query"
       - Restate the customer's core intent as a short, direct declarative statement.
       - Strip ALL conversational filler: 'please help me', 'I was wondering', 'could you
         tell me', 'hi there', greetings, apologies, and emotional language.
       - Resolve pronouns using the chat history (e.g. 'it' -> the specific product name;
         'my last order' -> the order number if mentioned earlier in the conversation).
       - Use domain-specific terminology where appropriate
         (e.g. 'refund' not 'get my money back'; 'return window' not 'how long I have').
       - Target length: one crisp sentence, 10-20 words.

    2. "hypothetical_answer"
       - Write a 2-4 sentence passage that *would* be the ideal answer if it appeared
         verbatim in an authoritative help-center article or policy document.
       - Use the vocabulary and phrasing that such a document would use — this is the
         HyDE (Hypothetical Document Embedding) technique: the goal is to move the query
         vector closer to real document chunk vectors in embedding space.
       - Mirror common help-center section structures: conditions, timeframes, steps,
         exceptions (e.g. "Customers may request a refund within 30 days of purchase...").
       - Do NOT fabricate specific numbers, dates, or policy details you cannot know —
         keep the content plausible but generic enough to match real documents.

    3. "keywords"
       - A list of 3-6 individual search terms: core domain concepts, synonyms, and
         likely section headings from a help center.
       - Include BOTH the customer's natural phrasing AND the formal/technical equivalent
         (e.g. ["return", "refund", "RMA", "30-day window", "exchange", "restocking fee"]).
       - Avoid stop words, filler words, and single characters.

    Rules:
    - Output ONLY valid JSON matching the schema. No markdown fences, no extra text,
      no commentary before or after the JSON.
    - If the question is too vague or generic to rewrite meaningfully (e.g. "help"),
      use the original verbatim as the declarative_query and return empty strings/lists
      for the other fields — do not hallucinate a direction.
    - Never answer the question yourself. Your ONLY job is query reformulation.
    - Never include PII (names, emails, order IDs) in the output fields.
    """),
    ("human",
     "Customer question: {original_query}\n\n"
     "Recent chat history (use for pronoun resolution and context only):\n{chat_history}")
])


from langchain_core.runnables.config import RunnableConfig

def rewrite_query_node(state: AgentState, config: RunnableConfig):
    """
    Transforms the user's raw query into structured search representations optimized for vector retrieval.
    
    Uses an LLM to generate a declarative statement, a hypothetical ideal answer (HyDE), and 
    keywords from the original query, taking chat history into account for context.
    
    Args:
        state (AgentState): The current state of the agent, containing the original query and chat history.
        config (RunnableConfig): Configuration containing the dynamic agent config.
        
    Returns:
        dict: A state update containing the 'rewritten_query' as a searchQueries object.
    """
    agent_config = config.get("configurable", {}).get("agent_config", {}).get("subagents", {}).get("retrieval_agent", {})
    llm = build_model(agent_config)
    structured_rewriter = llm.with_structured_output(searchQueries)
    query_rewrite_chain = rewrite_prompt | structured_rewriter

    result = query_rewrite_chain.invoke({
        "original_query": state["query"],
        "chat_history": state.get("messages", [])
    })
    return {"rewritten_query": result}

def vector_search_node(state: AgentState, config: RunnableConfig):
    """
    Executes a similarity search against the vector database using the rewritten query representations.
    
    Combines the declarative query and hypothetical answer to form a comprehensive search string, 
    then retrieves the top relevant document chunks from the pgvector database.
    
    Args:
        state (AgentState): The current state containing the 'rewritten_query'.
        config (RunnableConfig): Config containing workspace context.
        
    Returns:
        dict: A state update containing the 'retrieved_docs' (list of relevant documents).
    """
    queries = state["rewritten_query"]

    search_string = f"{queries.declarative_query}\n\n{queries.hypothetical_answer}"

    # Ensure workspace isolation
    filters = state.get("filters") or {}
    # If the orchestrator provided agent_config, it should have the workspace_id.
    agent_config = config.get("configurable", {}).get("agent_config", {})
    workspace_id = agent_config.get("workspace_id")
    if workspace_id:
        filters["workspace_id"] = str(workspace_id)

    doc_search_results = pgvector_client.similarity_search(
        query=search_string,
        top_k=state.get("top_k", 5),
        filter=filters
    )
    
    return {"retrieved_docs": doc_search_results}


def generate_answer_node(state: AgentState, config: RunnableConfig):
    """
    Synthesizes a final answer to the user's query based strictly on the retrieved document chunks.
    
    Constructs a prompt with the retrieved context and uses the LLM to generate an answer. 
    The answer must cite the specific source chunk IDs used. If the retrieved documents do not 
    contain sufficient information, the model should indicate insufficient coverage instead of hallucinating.
    
    Args:
        state (AgentState): The current state containing the 'query', 'messages', and 'retrieved_docs'.
        
    Returns:
        dict: A state update containing the 'final_response' and 'source_chunks' used.
    """
    source_chunks = []
    for doc in state["retrieved_docs"]:
        source_chunks.append(ChunkRef(
            chunk_id=doc.metadata.get("id", "unknown"),
            document_id=doc.metadata.get("document_id", "unknown"),
            similarity=doc.metadata.get("similarity", 0.0)
        ))

    docs_text = "\n\n".join([doc.page_content for doc in state["retrieved_docs"]])

    answer_prompt = f"""You are the Retrieval Agent in a multi-agent customer-support system.
    The Orchestrator has delegated this question to you because it requires knowledge-base lookup.
    Your job is to synthesise a grounded, accurate, customer-facing answer using ONLY the
    retrieved context passages provided below.

    ======================== STRICT RULES ========================

    1. GROUNDEDNESS
       - Answer using ONLY information present in the Context section below.
       - Do not add facts, figures, policies, prices, or timelines that are not explicitly
         stated in the context, even if you believe them to be true.
       - If the context contains a partial answer, give that partial answer and explicitly
         state what is not covered (e.g. "The context covers X but does not mention Y.").

    2. INSUFFICIENT COVERAGE
       - If the retrieved context does not contain enough information to answer the question,
         respond with exactly this phrase (and nothing else):
         "I don't have enough information in the knowledge base to answer this question."
       - Do not guess. Do not fill gaps with general knowledge. Do not hedge with
         'I think' or 'usually'. If the context doesn't say it, you don't say it.

    3. CITATIONS
       - Attribute statements to specific source passages wherever possible.
         Use the document title, section name, or chunk identifier visible in the context
         (e.g. "According to the Returns & Refunds Policy: ...").
       - If multiple chunks support a claim, cite all of them.

    4. TONE AND FORMAT
       - Professional, helpful, and concise — this response is delivered directly to a customer.
       - Use plain language; avoid internal jargon or system terminology unless the customer
         used it first.
       - Use numbered steps or bullet points ONLY when describing a process or a list of
         options; use prose for simple factual answers.
       - Do NOT pad the response with preamble ("Great question!", "Of course!", "Certainly!"),
         closing remarks ("I hope this helps!", "Let me know if you need anything else!"),
         or self-references ("As an AI...", "Based on my training...").
       - Aim for the shortest response that fully and accurately answers the question.

    5. SCOPE — WHAT YOU MUST NOT DO
       - You are READ-ONLY. Never instruct the customer to take an action that requires
         account changes, refunds, cancellations, or speaking to a specific person.
       - If the question clearly requires an account action, answer only what the knowledge
         base says about the policy/process, then append exactly one sentence:
         "The Orchestrator will handle the next steps for your account."
       - Never make up order IDs, ticket numbers, contact details, or URLs.

    ======================== QUESTION ========================
    {state['query']}

    ======================== RETRIEVED CONTEXT ========================
    {docs_text}

    ======================== YOUR ANSWER ========================
    """

    # Invoke LLM to synthesise a grounded answer from the retrieved documents
    agent_config = config.get("configurable", {}).get("agent_config", {}).get("subagents", {}).get("retrieval_agent", {})
    llm = build_model(agent_config)
    llm_response = llm.invoke(answer_prompt)
    answer_text = llm_response.content if hasattr(llm_response, "content") else str(llm_response)

    INSUFFICIENT_PHRASE = "I don't have enough information in the knowledge base to answer this question."
    insufficient_coverage = INSUFFICIENT_PHRASE in answer_text

    final_result = RetrievalResult(
        answer=answer_text,
        source_chunks=source_chunks,
        insufficient_coverage=insufficient_coverage
    )

    return {"final_response": final_result}


builder = StateGraph(AgentState)
builder.add_node("rewrite_query", rewrite_query_node)
builder.add_node("vector_search", vector_search_node)
builder.add_node("generate_answer", generate_answer_node)

builder.add_edge(START, "rewrite_query")
builder.add_edge("rewrite_query", "vector_search")
builder.add_edge("vector_search", "generate_answer")
builder.add_edge("generate_answer", END)

retrieval_agent = builder.compile()

# Decorate the retrieval agent with a tool. This allows the retrieval agent to be used as a tool in other agents.
@tool(args_schema=RetrievalRequest, name_or_callable="retrieval_agent")
def invoke_retrieval_agent(
    query: str,
    context_slice: list[str],
    config: RunnableConfig,
    top_k: int = 5,
    filters: dict | None = None
) -> RetrievalResult:
    """
    Invokes the retrieval subagent to search the vector database and generate an answer based on the retrieved context.
    
    This tool should be used when you need to answer questions that require looking up specific information, 
    documentation, or historical context that is not in your immediate context.
    
    Args:
        query: The search query or question to be answered by the retrieval agent.
        context_slice: Relevant context or conversation history to help the retrieval agent understand the query better.
        top_k: The number of relevant documents to retrieve from the vector database. Defaults to 5.
        filters: Optional metadata filters to apply during the vector search.
        
    Returns:
        A RetrievalResult containing the generated answer and the list of documents used to generate it.
    """
    initial_state = {
        "query": query,
        "messages": context_slice,
        "top_k": top_k,
        "filters": filters
    }
    
    result_state = retrieval_agent.invoke(initial_state, config=config)
    
    return result_state["final_response"]    