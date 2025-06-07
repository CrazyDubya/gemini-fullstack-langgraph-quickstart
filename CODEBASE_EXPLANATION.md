# Codebase Explanation

## Project Overview and Purpose

This project is a fullstack application featuring a React frontend and a versatile LangGraph-powered backend agent. The agent is capable of performing multiple tasks:

1.  **Comprehensive Research**: Dynamically generates search terms, queries the web using Google Search and ArXiv for academic papers, processes uploaded PDF documents, reflects on results to identify knowledge gaps, and iteratively refines its search to provide well-supported answers with citations.
2.  **Codebase Question Answering**: Answers questions based *only* on the content of a provided document (specifically, this `CODEBASE_EXPLANATION.md` itself), without performing external searches.
3.  **URL Summarization**: Fetches content from a user-provided URL and generates a concise summary.

The application demonstrates building advanced, multi-functional conversational AI using LangGraph, Google's Gemini models, and various tools. The frontend supports user interactions, including (mocked) user accounts for chat history persistence and PDF file uploads.

## Technologies Used

-   **Frontend:**
    -   [React](https://reactjs.org/) (with [Vite](https://vitejs.dev/))
    -   [Tailwind CSS](https://tailwindcss.com/)
    -   [Shadcn UI](https://ui.shadcn.com/)
-   **Backend:**
    -   [LangGraph](https://github.com/langchain-ai/langgraph)
    -   [FastAPI](https://fastapi.tiangolo.com/)
    -   [Google Gemini](https://ai.google.dev/models/gemini) LLM
    -   [PyPDF2](https://pypi.org/project/PyPDF2/) (for PDF text extraction)
    -   [arxiv](https://pypi.org/project/arxiv/) (Python wrapper for ArXiv API)
    -   `python-multipart` (for FastAPI file uploads)

## Project Structure

The project is divided into two main directories:

-   `frontend/`: Contains the React application.
-   `backend/`: Contains the LangGraph/FastAPI application, including the agent logic and API endpoints. The agent's graph definition is in `backend/src/agent/graph.py`.

## Backend Agent Workflow (`backend/src/agent/graph.py`)

The backend agent is built using LangGraph and follows a stateful, graph-based approach. It can perform different tasks based on an initial `task_type` parameter.

**Core Agent States (in `backend/src/agent/state.py`)**:

-   `OverallState`: The central state dictionary holding all information, including:
    -   `messages`: The history of conversation.
    -   `task_type`: Specifies the current task (e.g., "research", "codebase_qa", "url_summary").
    -   Research-specific fields: `query_list`, `web_research_result`, `pdf_research_result`, `arxiv_research_result`, `sources_gathered`, `uploaded_pdf_info`, etc.
    -   Codebase Q&A specific field: `codebase_context`.
    -   URL Summarization specific field: `target_url`.
-   `ReflectionState`: Holds outputs from the reflection step during research.

**Task Routing (`task_router_node`)**:

-   The graph execution begins with `task_router_node`.
-   This node inspects `state.get("task_type")`:
    -   If "codebase_qa" (and `codebase_context` is present), it routes to `codebase_qa_answer_node`.
    -   If "url_summary" (and `target_url` is present), it routes to `url_summary_node`.
    -   Otherwise (or if required context for a special task is missing), it defaults to the "research" flow by routing to `generate_query`.

**1. Research Task Flow**:

This is the most complex flow, designed for in-depth information gathering.

-   **`generate_query` (Node)**:
    -   Generates initial search queries based on the user's question using an LLM.
-   **`pdf_research_node` (Node)**:
    -   If `uploaded_pdf_info` (containing name and server path of an uploaded PDF) is present in the state, this node uses the `PDFTextExtractionTool` (which uses `PyPDF2`) to extract text from the specified PDF(s).
    -   The extracted text is added to `state['pdf_research_result']`. This content is then available for reflection and final answer generation.
-   **`initial_web_research_dispatcher_node` (Node)**:
    -   Takes the `query_list` from `generate_query`.
    -   Dispatches individual search tasks to the `web_research` worker node for each query using LangGraph's `Send` mechanism.
-   **`web_research` (Worker Node)**:
    -   Receives a single search query.
    -   Uses a Gemini model with the Google Search API tool (`genai_client.models.generate_content`) to find relevant web pages.
    -   Extracts content and citation information, storing results in `web_research_result` and `sources_gathered`.
-   **`arxiv_research_node` (Worker Node - for follow-ups)**:
    -   Receives a search query intended for ArXiv.
    -   Uses the `ArxivSearchTool` (which uses the `arxiv` library) to find academic papers.
    -   Formats results (title, summary, authors, PDF link) into a text string.
    -   Appends this string to `state['arxiv_research_result']`.
-   **`reflection_node` (Node)**:
    -   Consolidates all gathered information: `web_research_result`, `pdf_research_result`, and `arxiv_research_result`.
    -   Uses an LLM with `reflection_instructions` prompt to analyze the information.
    -   Determines if the information is sufficient (`is_sufficient`).
    *   Identifies knowledge gaps (`knowledge_gap`).
    *   Suggests `follow_up_queries`. Each follow-up query is now a dictionary specifying its `type` (e.g., "web", "arxiv") and the `query` string. This allows the agent to decide which search tool to use for follow-ups.
-   **`evaluate_research_conditional_router` (Conditional Edge Logic)**:
    -   If `is_sufficient` is true or max research loops are reached, routes to `finalize_answer_node`.
    -   Else, if `follow_up_queries` exist, routes to `followup_research_dispatcher_node`.
-   **`followup_research_dispatcher_node` (Node)**:
    -   Iterates through the `follow_up_queries` from the reflection step.
    -   If a query `type` is "arxiv", it dispatches a task to `arxiv_research_node`.
    -   Otherwise (defaulting to "web"), it dispatches to `web_research_node`.
-   **Looping**: After tasks from `followup_research_dispatcher_node` are processed (i.e., `web_research` or `arxiv_research_node` complete), the graph routes back to `reflection_node` to evaluate the newly gathered information.
-   **`finalize_answer_node` (Node)**:
    -   Consolidates all research results one last time (web, PDF, ArXiv).
    -   Uses an LLM with `answer_instructions` prompt to synthesize a final, comprehensive answer, including web citations.
    -   The final answer is stored as an `AIMessage`.

**2. Codebase Question Answering Task Flow (`codebase_qa_answer_node`)**:

-   This flow is invoked if `task_type` is "codebase_qa".
-   It uses the `codebase_qa_prompt`.
-   The primary input is `state['codebase_context']`, which is intended to be populated with the content of this `CODEBASE_EXPLANATION.md` document by the calling application (e.g., `app.py`).
-   The LLM answers the user's question based *solely* on this provided context, without any external searches or tool usage.
-   The answer is stored as an `AIMessage`. This node connects directly to `END`.

**3. URL Summarization Task Flow (`url_summary_node`)**:

-   Invoked if `task_type` is "url_summary".
-   Uses the `url_summarizer_prompt`.
-   Takes `state['target_url']` (a user-provided URL).
-   It invokes an LLM, similar to `web_research`, enabling the `google_search` tool. The prompt specifically instructs the LLM to use its browsing capability to fetch content from the `target_url` and summarize it.
-   The generated summary is stored as an `AIMessage`. This node connects directly to `END`.

**Graph Compilation**:
The graph is compiled with the name "configurable-agent".

## Frontend Components and Data Flow (`frontend/src/App.tsx`, etc.)

The React frontend allows users to interact with the various agent capabilities.

**Key Frontend Features & Flow**:

-   **User Authentication (Mocked)**:
    -   `App.tsx` manages a `currentUser` state.
    -   If no user is logged in, a simple form prompts for a username.
    -   Upon submission, the username is stored in `localStorage`. There's no backend password authentication.
    -   A "Logout" button clears the user from `localStorage` and resets the session.
-   **Chat History**:
    -   Chat messages (`Message[]`) are stored in `localStorage`, keyed by the username (`chatHistory_[username]`).
    -   When a user logs in, their past chat history is loaded into the `chatMessages` state in `App.tsx`.
    -   The `useStream` hook (from `@langchain/langgraph-sdk/react`) is initialized with this loaded history using `thread.replace()`.
    -   As new messages are streamed from the backend or sent by the user, the combined history in `chatMessages` is updated and re-saved to `localStorage`.
    -   `handleSubmit` in `App.tsx` sends the complete message history (loaded + new) to the backend agent.
-   **PDF Upload**:
    -   `InputForm.tsx` includes a file input (`<input type="file" accept=".pdf" />`) triggered by a paperclip icon.
    -   When a file is selected, `App.tsx`'s `handleSubmit` function is informed.
    -   `handleSubmit` first uploads the selected PDF to a backend endpoint (`/upload_pdf/`) using `fetch` and `FormData`.
    -   The backend saves the PDF to a temporary server directory (e.g., `temp_pdfs/`) and returns its name and server path.
    -   `App.tsx` stores this PDF information (name and path) in `uploadedPdfInfo` state.
    -   This `uploadedPdfInfo` is then included in the payload to the agent (`thread.submit()`) when the user sends their query, allowing the `pdf_research_node` in the backend to access it.
    -   The `uploadedPdfInfo` is cleared after the submission to prevent re-processing with unrelated queries.
    -   The name of an uploaded/selected file is displayed in the UI near the input area.
-   **Interaction with Agent Tasks**:
    -   The frontend doesn't explicitly set `task_type`. This is currently a backend configuration or would need UI elements to select a task type, which then `app.py` would use to initialize the agent state. For now, the "research" task is the default if no other task is specified by the backend setup. To use Codebase Q&A or URL Summarization, the initial call to the agent graph from `app.py` would need to set `task_type` and the relevant context (`codebase_context` or `target_url`).

**Backend API Endpoint for PDF Upload**:
-   A new POST endpoint `/upload_pdf/` in `backend/src/agent/app.py` handles PDF file uploads from the frontend.

## Setup and Development Instructions (Summarized from README.md)

**1. Prerequisites:**

-   Node.js and npm (or yarn/pnpm)
-   Python 3.8+
-   **`GEMINI_API_KEY`**:
    1.  Go to `backend/`.
    2.  Copy `backend/.env.example` to `.env`.
    3.  Add your Gemini API key to `.env`: `GEMINI_API_KEY="YOUR_ACTUAL_API_KEY"`

**2. Install Dependencies:**

-   **Backend:**
    ```bash
    cd backend
    pip install .
    ```
-   **Frontend:**
    ```bash
    cd frontend
    npm install
    ```

**3. Run Development Servers:**

-   **Both Backend & Frontend (from project root):**
    ```bash
    make dev
    ```
    -   Frontend will be at `http://localhost:5173/app`.
    -   Backend API at `http://127.0.0.1:2024`.

-   **Alternatively, run separately:**
    -   **Backend (`backend/` directory):** `langgraph dev`
    -   **Frontend (`frontend/` directory):** `npm run dev`

The `apiUrl` in `frontend/src/App.tsx` is set to `http://localhost:2024` for development and `http://localhost:8123` for the Docker Compose production setup.

## Leveraging the Codebase

This enhanced codebase offers a robust platform for various AI-driven information processing tasks. Potential extensions and use cases include:

-   **Expanding Toolset**: Integrate more tools into the research flow (e.g., specific database readers, other APIs like Wikipedia, financial data services). The reflection mechanism can be taught to suggest these tools.
-   **Task-Specific UI**: Develop UI components in the frontend to explicitly select the desired `task_type` (Research, Codebase Q&A, URL Summary) and provide the necessary inputs (e.g., a field for `target_url`).
-   **Advanced PDF Interaction**: Instead of just text extraction, allow for Q&A over uploaded PDFs, or use the ArXiv PDF links for direct Q&A with those papers.
-   **Refined Citation for ArXiv**: Extract more structured metadata from ArXiv results and display it more formally in the final answer, potentially linking directly to the ArXiv page or PDF.
-   **Error Handling and UX**: Improve frontend error handling for API calls (PDF upload, agent interaction) and provide clearer user feedback.
-   **Production Deployment**: For real-world use, implement proper user authentication, secure file management (with cleanup), and robust API security for the backend.
-   **Fine-tuning Models**: For highly specialized Q&A or summarization tasks, fine-tune LLMs on domain-specific datasets.
-   **Interactive Task Configuration**: Allow users to configure agent parameters (e.g., number of search results, summarization length) through the UI.
