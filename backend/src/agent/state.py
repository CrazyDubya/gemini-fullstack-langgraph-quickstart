from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import add_messages
from typing_extensions import Annotated
from typing import Optional, List, Dict

import operator
from dataclasses import dataclass, field
from typing_extensions import Annotated


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str
    uploaded_pdf_info: Optional[List[Dict[str, str]]] = None # [{"name": "filename.pdf", "path": "/path/to/file.pdf"}]
    pdf_research_result: Annotated[Optional[list], operator.add] = None
    # For Codebase Q&A task
    codebase_context: Optional[str] = None
    task_type: Optional[str] = None # e.g., "research", "codebase_qa", "url_summary"
    # For URL Summarization task
    target_url: Optional[str] = None
    # For ArXiv Search
    arxiv_research_result: Annotated[Optional[list], operator.add] = None


class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int


class Query(TypedDict):
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    query_list: list[Query] # This is output of query_writer, List[Dict[str,str]]
    # query_list from generate_query node is List[str], so we might need a different name
    # or ensure generate_query output matches this if QueryGenerationState is used as a direct state key.
    # For now, generate_query populates 'query_list' in OverallState as List[str].
    # Let's keep QueryGenerationState for the node's direct output type hint.


class WebSearchState(TypedDict):
    search_query: str
    id: str


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report
