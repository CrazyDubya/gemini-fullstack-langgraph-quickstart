from typing import List, Dict
from pydantic import BaseModel, Field
import arxiv # For ArxivSearchTool


class SearchQueryList(BaseModel):
    query: List[str] = Field(
        description="A list of search queries to be used for web research."
    )
    rationale: str = Field(
        description="A brief explanation of why these queries are relevant to the research topic."
    )


class Reflection(BaseModel):
    is_sufficient: bool = Field(
        description="Whether the provided summaries are sufficient to answer the user's question."
    )
    knowledge_gap: str = Field(
        description="A description of what information is missing or needs clarification."
    )
    follow_up_queries: List[Dict[str, str]] = Field(
        description=(
            "A list of follow-up queries to address the knowledge gap. "
            "Each query should be a dictionary with 'type' (e.g., 'web', 'arxiv') and 'query' (the search string)."
        )
    )


class PDFTextExtractionInput(BaseModel):
    file_path: str = Field(description="The path to the PDF file to be processed.")


from langchain_core.tools import BaseTool
from PyPDF2 import PdfReader
import io

class PDFTextExtractionTool(BaseTool):
    name: str = "pdf_text_extractor"
    description: str = "Extracts text content from a PDF file."
    args_schema: type[BaseModel] = PDFTextExtractionInput

    def _run(self, file_path: str) -> str:
        try:
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            if not text:
                return "No text could be extracted from the PDF."
            return text
        except Exception as e:
            return f"Error extracting text from PDF: {e}"

    async def _arun(self, file_path: str) -> str:
        # For simplicity, using the sync version. Implement async if needed.
        return self._run(file_path)


class ArxivSearchInput(BaseModel):
    query: str = Field(description="The search query for ArXiv.")
    max_results: int = Field(
        default=3, description="Maximum number of results to return."
    )


class ArxivSearchTool(BaseTool):
    name: str = "arxiv_search"
    description: str = (
        "Searches ArXiv for academic papers and returns a list of results."
    )
    args_schema: type[BaseModel] = ArxivSearchInput

    def _run(self, query: str, max_results: int = 3) -> str:
        try:
            search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
            results = []
            for r in search.results():
                result_str = (
                    f"Title: {r.title}\n"
                    f"Authors: {', '.join(auth.name for auth in r.authors)}\n"
                    f"Published: {r.published.strftime('%Y-%m-%d')}\n"
                    f"Summary: {r.summary}\n"
                    f"PDF Link: {r.pdf_url}\n"
                    f"Primary Category: {r.primary_category}\n"
                    f"Categories: {r.categories}\n"
                    f"Comment: {r.comment}\n"
                    f"DOI: {r.doi}\n"
                    f"Journal Reference: {r.journal_ref}"
                )
                results.append(result_str)
            if not results:
                return f"No results found on ArXiv for query: {query}"
            return "\n\n---\n\n".join(results)
        except Exception as e:
            return f"Error during ArXiv search for query '{query}': {e}"

    async def _arun(self, query: str, max_results: int = 3) -> str:
        # For simplicity, using the sync version. Implement async if needed for true async behavior.
        return self._run(query=query, max_results=max_results)
