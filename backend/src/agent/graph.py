import os

from agent.tools_and_schemas import (
    SearchQueryList,
    Reflection,
    PDFTextExtractionTool,
    ArxivSearchTool, # Added ArxivSearchTool
)
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langgraph.types import Send
from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langchain_core.runnables import RunnableConfig
from google.genai import Client

from agent.state import (
    OverallState,
    QueryGenerationState,
    ReflectionState,
    WebSearchState,
)
from agent.configuration import Configuration
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
)
from agent.prompts import codebase_qa_prompt, url_summarizer_prompt

load_dotenv()

if os.getenv("GEMINI_API_KEY") is None:
    raise ValueError("GEMINI_API_KEY is not set")

# Used for Google Search API
genai_client = Client(api_key=os.getenv("GEMINI_API_KEY"))


# Nodes
def generate_query(state: OverallState, config: RunnableConfig) -> QueryGenerationState:
    """LangGraph node that generates a search queries based on the User's question.

    Uses Gemini 2.0 Flash to create an optimized search query for web research based on
    the User's question.

    Args:
        state: Current graph state containing the User's question
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated query
    """
    configurable = Configuration.from_runnable_config(config)

    # check for custom initial search query count
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    # init Gemini 2.0 Flash
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=1.0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(SearchQueryList)

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        number_queries=state["initial_search_query_count"],
    )
    # Generate the search queries
    result = structured_llm.invoke(formatted_prompt)
    return {"query_list": result.query}


def continue_to_web_research(state: QueryGenerationState):
    """LangGraph node that sends the search queries to the web research node.

    This is used to spawn n number of web research nodes, one for each search query.
    """
    sends = [
        Send("web_research", {"search_query": search_query, "id": int(idx)})
        for idx, search_query in enumerate(state["query_list"])
    ]
    # This node's logic is now part of initial_web_research_dispatcher
    # For now, we'll keep the old conditional routing to ensure graph compiles,
    # but it will be replaced by a direct edge or a simpler router.
    # This function is no longer used as a conditional router for generate_query
    # It can be removed or repurposed if needed elsewhere.
    # For now, its logic is superseded by the new task_router_node and direct graph edges.
    pass


def task_router_node(state: OverallState) -> str:
    """Routes based on the task_type field in the state."""
    task = state.get("task_type")
    if task == "codebase_qa":
        if state.get("codebase_context"):
            return "codebase_qa_answer"
        else:
            print("Warning: task_type 'codebase_qa' but codebase_context is missing. Falling back to research.")
            return "generate_query"
    elif task == "url_summary":
        if state.get("target_url"):
            return "url_summary"
        else:
            print("Warning: task_type 'url_summary' but target_url is missing. Falling back to research.")
            return "generate_query"
    return "generate_query" # Default to research flow


def url_summary_node(state: OverallState, config: RunnableConfig):
    """Fetches content from a target URL and summarizes it."""
    configurable = Configuration.from_runnable_config(config)
    # Use a specific model or the general reasoning_model
    model_name = state.get("reasoning_model") or configurable.reasoning_model
    target_url = state.get("target_url")

    if not target_url:
        return {"messages": [AIMessage(content="Error: Target URL is missing for summarization task.")]}

    # The user's actual "question" for this task is the URL itself, implicitly.
    # We can use get_research_topic to see if there's other instructional text,
    # or just use the URL directly in the prompt.
    # For this task, the main input to the prompt is the URL.
    # The user messages might contain "Summarize this URL: http://example.com"
    # get_research_topic gets the last human message.

    formatted_prompt = url_summarizer_prompt.format(
        url=target_url,
        current_date=get_current_date(),
    )

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.7, # Moderate temperature for summarization
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    # To enable the LLM to fetch the URL, use the google_search tool.
    # The prompt guides the LLM to use this tool for the specific URL.
    # Note: genai_client.models.generate_content is used here like in web_research for tool use.
    # If ChatGoogleGenerativeAI's .invoke() can directly use tools in a structured way,
    # that could be an alternative, but this pattern is established in the codebase.

    try:
        response = genai_client.models.generate_content(
            model=model_name, # Ensure this is a model that supports function calling/tools
            contents=formatted_prompt,
            generation_config={"temperature": 0.7}, # Ensure temperature is passed if supported this way
            tools=[{"google_search": {}}], # Enable Google Search tool
        )
        # The response.text should contain the summary if the LLM followed instructions.
        # No explicit grounding_metadata is expected to be parsed here as in web_search,
        # as the summary is the direct output.
        summary_text = response.text
        if not summary_text: # Check if response.text is empty
             summary_text = f"Could not retrieve or summarize content from {target_url}. The content might be inaccessible or the model could not perform the summarization."

    except Exception as e:
        print(f"Error during URL summarization call: {e}")
        summary_text = f"An error occurred while trying to summarize the URL {target_url}: {e}"

    return {"messages": [AIMessage(content=summary_text)], "sources_gathered": []}


def codebase_qa_answer_node(state: OverallState, config: RunnableConfig):
    """Generates an answer for a codebase question using only the provided context."""
    configurable = Configuration.from_runnable_config(config)
    # Use a default reasoning model or allow configuration
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model

    user_question = get_research_topic(state["messages"]) # Gets the latest human message
    code_context = state.get("codebase_context")

    if not code_context:
        # This should ideally be caught by the router or an earlier validation step
        return {"messages": [AIMessage(content="Error: Codebase context is missing for Q&A task.")]}

    formatted_prompt = codebase_qa_prompt.format(
        user_question=user_question,
        codebase_context=code_context,
    )

    llm = ChatGoogleGenerativeAI(
        model=reasoning_model, # Or a specific model for Q&A if desired
        temperature=0, # Low temperature for factual answers from context
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result_message = llm.invoke(formatted_prompt)

    # No sources to cite for codebase Q&A from a single document
    return {"messages": [AIMessage(content=result_message.content)], "sources_gathered": []}


def web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using the native Google Search API tool.

    Executes a web search using the native Google Search API tool in combination with Gemini 2.0 Flash.

    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings

    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    # Configure
    configurable = Configuration.from_runnable_config(config)
    formatted_prompt = web_searcher_instructions.format(
        current_date=get_current_date(),
        research_topic=state["search_query"],
    )

    # Uses the google genai client as the langchain client doesn't return grounding metadata
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=formatted_prompt,
        config={
            "tools": [{"google_search": {}}],
            "temperature": 0,
        },
    )
    # resolve the urls to short urls for saving tokens and time
    resolved_urls = resolve_urls(
        response.candidates[0].grounding_metadata.grounding_chunks, state["id"]
    )
    # Gets the citations and adds them to the generated text
    citations = get_citations(response, resolved_urls)
    modified_text = insert_citation_markers(response.text, citations)
    sources_gathered = [item for citation in citations for item in citation["segments"]]

    return {
        "sources_gathered": sources_gathered,
        "search_query": [state["search_query"]], # Storing the original query for this result
        "web_research_result": [modified_text],
    }


def pdf_research_node(state: OverallState, config: RunnableConfig) -> OverallState:
    """LangGraph node that extracts text from uploaded PDF files.

    Uses the PDFTextExtractionTool to get text content from PDF files specified
    in the state's uploaded_pdf_info. Appends results to pdf_research_result list.
    Does nothing if no PDFs are uploaded.
    """
    pdf_info_list = state.get("uploaded_pdf_info")
    if not pdf_info_list:
        # Return current pdf_research_result if it exists, or empty list
        return {"pdf_research_result": state.get("pdf_research_result") or []}

    all_pdf_texts = state.get("pdf_research_result") or []
    pdf_tool = PDFTextExtractionTool()

    for pdf_info in pdf_info_list:
        file_path = pdf_info.get("path")
        file_name = pdf_info.get("name", "Unknown PDF")
        if file_path:
            try:
                # Ensure the tool is invoked correctly if it's a Runnable
                extracted_text = pdf_tool.invoke({"file_path": file_path})
                all_pdf_texts.append(f"Content from PDF '{file_name}':\n{extracted_text}")
            except Exception as e:
                all_pdf_texts.append(f"Error processing PDF '{file_name}': {e}")
        else:
            all_pdf_texts.append(f"Error: No path provided for PDF '{file_name}'.")

    # Clear uploaded_pdf_info after processing to avoid reprocessing, if desired,
    # or manage this via explicit state flags. For now, let's assume it's processed once.
    return {"pdf_research_result": all_pdf_texts, "uploaded_pdf_info": None}


def initial_web_research_dispatcher_node(state: OverallState) -> list[Send]:
    """Dispatches web research tasks for initial queries from generate_query."""
    query_list = state.get("query_list", [])
    sends = []
    if query_list:
        for idx, query_str in enumerate(query_list):
            # Assuming query_list is now just List[str] based on generate_query output
            sends.append(Send("web_research", {"search_query": query_str, "id": idx}))
    # This node itself doesn't update state directly other than what Send might imply
    # It returns a list of Send calls, which LangGraph executes.
    # If sends is empty, LangGraph proceeds along the static edge from this node.
    return sends


def followup_research_dispatcher_node(state: OverallState) -> list[Send]:
    """Dispatches web or ArXiv research tasks for follow-up queries from reflection."""
    follow_up_queries = state.get("follow_up_queries", []) # This is now List[Dict[str, str]]
    sends = []
    offset = state.get("number_of_ran_queries", 0) # To maintain unique IDs for web results

    if follow_up_queries:
        for idx, item in enumerate(follow_up_queries):
            query_type = item.get("type", "web") # Default to web search
            query_str = item.get("query")

            if not query_str:
                continue # Skip if query is empty

            if query_type == "arxiv":
                # ArxivSearchTool might not need an ID in the same way web_research does for citation tracking.
                # For now, let's pass a generic or no ID, or adapt Arxiv node if needed.
                # The ArxivSearchTool itself takes 'query' and 'max_results'.
                # We'll assume Arxiv node handles this. The 'id' might be for state tracking if mapped.
                sends.append(Send("arxiv_research", {"search_query": query_str}))
            else: # Default to web search
                sends.append(Send("web_research", {"search_query": query_str, "id": offset + idx}))
    return sends

# ArXiv Research Node
def arxiv_research_node(state: OverallState, config: RunnableConfig) -> OverallState:
    """Performs an ArXiv search using the ArxivSearchTool and appends results."""
    # The input 'search_query' will be passed via the Send() call from the dispatcher
    query = state.get("search_query") # This relies on Send populating this key in the state for this node
    if not query:
        # This might happen if the node is called without a proper Send dispatch
        print("Warning: arxiv_research_node called without a search_query in state.")
        return {"arxiv_research_result": state.get("arxiv_research_result") or []}

    arxiv_tool = ArxivSearchTool()
    try:
        # Assuming ArxivSearchTool takes query and returns a formatted string
        # The tool's default max_results is 3. Can be made configurable if needed.
        result_str = arxiv_tool.invoke({"query": query})
    except Exception as e:
        result_str = f"Error during ArXiv search for query '{query}': {e}"

    current_results = state.get("arxiv_research_result") or []
    current_results.append(result_str)

    return {"arxiv_research_result": current_results}


def reflection_node(state: OverallState, config: RunnableConfig) -> ReflectionState:
    """LangGraph node that identifies knowledge gaps and generates potential follow-up queries.

    Analyzes the current summary to identify areas for further research and generates
    potential follow-up queries. Uses structured output to extract
    the follow-up query in JSON format.

    Args:
        state: Current graph state containing the running summary and research topic
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated follow-up query
    """
    configurable = Configuration.from_runnable_config(config)
    research_loop_count = state.get("research_loop_count", 0) + 1
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model

    current_date = get_current_date()
    # Consolidate all gathered information for reflection
    web_results = state.get("web_research_result") or []
    pdf_results = state.get("pdf_research_result") or []
    arxiv_results = state.get("arxiv_research_result") or []
    all_summaries = web_results + pdf_results + arxiv_results

    # Filter out any None or empty strings from summaries, just in case
    all_summaries = [str(s) for s in all_summaries if s and str(s).strip()]


    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(all_summaries if all_summaries else ["No information gathered yet."]),
    )

    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=1.0, # Higher temperature for creative reflection/gap identification
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(Reflection)
    result = structured_llm.invoke(formatted_prompt)

    # Update total number of queries run so far (web queries)
    # search_query in state is a list of queries that have been run and produced a web_research_result
    # This might need adjustment if we want to count PDF processing as a "query"
    number_of_ran_queries = len(state.get("search_query", []))

    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": result.follow_up_queries or [], # Ensure it's a list
        "research_loop_count": research_loop_count,
        "number_of_ran_queries": number_of_ran_queries, # For unique ID generation in followup
    }


def evaluate_research_conditional_router(state: OverallState, config: RunnableConfig) -> str:
    """Determines if research is sufficient or if follow-up is needed."""
    configurable = Configuration.from_runnable_config(config)
    # state contains reflection outputs: is_sufficient, follow_up_queries, research_loop_count
    max_loops = state.get("max_research_loops", configurable.max_research_loops)

    if state.get("is_sufficient") or state.get("research_loop_count", 0) >= max_loops:
        return "finalize_answer"
    # Check if follow_up_queries is not empty and contains actual queries
    elif state.get("follow_up_queries") and any(q.get("query") for q in state.get("follow_up_queries", [])):
        return "dispatch_followup_research" # Renamed from "dispatch_followup_web_research"
    else:
        return "finalize_answer"


def finalize_answer_node(state: OverallState, config: RunnableConfig):
    """LangGraph node that finalizes the research summary.

    Prepares the final output by deduplicating and formatting sources, then
    combining them with the running summary to create a well-structured
    research report with proper citations.

    Args:
        state: Current graph state containing the running summary and sources gathered

    Returns:
        Dictionary with state update, including running_summary key containing the formatted final summary with sources
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reasoning_model
    current_date = get_current_date()

    # Consolidate all gathered information for the final answer
    web_results = state.get("web_research_result") or []
    pdf_results = state.get("pdf_research_result") or []
    arxiv_results = state.get("arxiv_research_result") or []
    all_summaries = web_results + pdf_results + arxiv_results
    all_summaries = [str(s) for s in all_summaries if s and str(s).strip()]

    formatted_prompt = answer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(all_summaries if all_summaries else ["No information gathered to provide a final answer."]),
    )

    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0, # Low temperature for factual, synthesized answer
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result_message = llm.invoke(formatted_prompt)

    # Process sources for citation (ensure sources_gathered is a list)
    processed_content = result_message.content
    unique_sources = []
    # sources_gathered should be a list of dicts from web_research node
    # PDF content currently doesn't have structured sources like web_research does.
    # This part might need enhancement if PDF sources need to be cited.
    gathered_sources_list = state.get("sources_gathered", [])
    if not isinstance(gathered_sources_list, list): # defensive check
        gathered_sources_list = []

    for source in gathered_sources_list:
        # Ensure source is a dictionary and has 'short_url'
        if isinstance(source, dict) and "short_url" in source and source["short_url"] in processed_content:
            processed_content = processed_content.replace(source["short_url"], source["value"])
            unique_sources.append(source)

    # Clear out intermediate results if desired
    final_state_update = {
        "messages": [AIMessage(content=processed_content)],
        "sources_gathered": unique_sources,
        "web_research_result": [],
        "pdf_research_result": [],
        "arxiv_research_result": [], # Clear ArXiv results
        "query_list": [],
        "follow_up_queries": [], # Clear follow-up queries
    }
    return final_state_update


# Create Agent Graph
builder = StateGraph(OverallState, config_schema=Configuration)

# Add Nodes
# Router to decide between Codebase Q&A and Research tasks
builder.add_node("task_router", task_router_node)

# Nodes for Research Task
builder.add_node("generate_query", generate_query)
builder.add_node("pdf_research", pdf_research_node)
builder.add_node("initial_web_research_dispatcher", initial_web_research_dispatcher_node)
builder.add_node("web_research", web_research)
builder.add_node("arxiv_research", arxiv_research_node) # Added ArXiv research node
builder.add_node("reflection", reflection_node)
# Renamed followup_web_research_dispatcher to followup_research_dispatcher
builder.add_node("followup_research_dispatcher", followup_research_dispatcher_node)
builder.add_node("finalize_answer", finalize_answer_node)

# Node for Codebase Q&A Task
builder.add_node("codebase_qa_answer", codebase_qa_answer_node)

# Node for URL Summarization Task
builder.add_node("url_summary", url_summary_node)


# Define Edges

# Start with the task router
builder.add_conditional_edges(
    START,
    lambda state: task_router_node(state),
    {
        "codebase_qa_answer": "codebase_qa_answer",
        "url_summary": "url_summary", # Route to url_summary node
        "generate_query": "generate_query",
    },
)

# Edges for Research Task Flow
builder.add_edge("generate_query", "pdf_research")
builder.add_edge("pdf_research", "initial_web_research_dispatcher")
builder.add_edge("initial_web_research_dispatcher", "reflection")

builder.add_conditional_edges(
    "reflection",
    evaluate_research_conditional_router,
    {
        "finalize_answer": "finalize_answer",
        "dispatch_followup_web_research": "followup_web_research_dispatcher",
    },
)
builder.add_edge("followup_web_research_dispatcher", "reflection")
builder.add_edge("finalize_answer", END)

# Edge for Codebase Q&A Task Flow
builder.add_edge("codebase_qa_answer", END)

# Edge for URL Summarization Task Flow
builder.add_edge("url_summary", END)


# Compile the graph
graph = builder.compile(name="configurable-agent")
