# Codebase Explanation

## Project Overview and Purpose

This project is a fullstack application that uses a React frontend and a LangGraph-powered backend agent. The agent is designed to perform comprehensive research on a user's query. It dynamically generates search terms, queries the web using Google Search, reflects on the results to identify knowledge gaps, and iteratively refines its search until it can provide a well-supported answer with citations. This application serves as an example of building research-augmented conversational AI using LangGraph and Google's Gemini models.

## Technologies Used

-   **Frontend:**
    -   [React](https://reactjs.org/) (with [Vite](https://vitejs.dev/))
    -   [Tailwind CSS](https://tailwindcss.com/)
    -   [Shadcn UI](https://ui.shadcn.com/)
-   **Backend:**
    -   [LangGraph](https://github.com/langchain-ai/langgraph)
    -   [FastAPI](https://fastapi.tiangolo.com/)
    -   [Google Gemini](https://ai.google.dev/models/gemini) LLM

## Project Structure

The project is divided into two main directories:

-   `frontend/`: Contains the React application.
-   `backend/`: Contains the LangGraph/FastAPI application, including the research agent logic.

## Backend Agent Workflow (`backend/src/agent/graph.py`)

The backend agent is built using LangGraph and follows a stateful graph-based approach to process user queries.

**States:**

The agent transitions through several states defined in `agent/state.py`:

-   `OverallState`: Represents the overall state of the agent, including messages, query lists, research results, and loop counts.
-   `QueryGenerationState`: State related to generating search queries.
-   `ReflectionState`: State related to reflecting on search results and identifying knowledge gaps.
-   `WebSearchState`: State related to performing web searches.

**Core Nodes and Logic:**

1.  **`generate_query` (Node):**
    -   Takes the user's question from the `OverallState`.
    -   Uses a Gemini model (`configurable.query_generator_model`) to generate a list of initial search queries.
    -   The number of initial queries can be configured (`initial_search_query_count`).
    -   Outputs a `QueryGenerationState` with the `query_list`.

2.  **`continue_to_web_research` (Node):**
    -   Receives the `query_list` from `generate_query`.
    -   Spawns multiple `web_research` tasks, one for each search query, by sending messages to the `web_research` node.

3.  **`web_research` (Node):**
    -   Receives a `search_query` and an `id`.
    -   Uses the `genai_client` (Google Search API) and a Gemini model (`configurable.query_generator_model`) to perform a web search for the given query.
    -   Resolves URLs found in the search results to shorter versions.
    -   Extracts citations and inserts citation markers into the search result text.
    -   Outputs an `OverallState` update with `sources_gathered`, the original `search_query`, and the `web_research_result` (text with citations).

4.  **`reflection` (Node):**
    -   Receives the accumulated `web_research_result` from previous steps.
    -   Increments the `research_loop_count`.
    -   Uses a Gemini model (`configurable.reasoning_model`) to analyze the gathered summaries.
    -   Determines if the information is `is_sufficient` to answer the user's topic.
    -   Identifies any `knowledge_gap`.
    -   Generates `follow_up_queries` if more information is needed.
    -   Outputs a `ReflectionState` with these findings.

5.  **`evaluate_research` (Conditional Edge):**
    -   Receives the `ReflectionState`.
    -   Checks if `is_sufficient` is true OR if the `research_loop_count` has reached the `max_research_loops` (configurable).
    -   If true, routes to `finalize_answer`.
    -   Otherwise, routes back to `web_research` with the `follow_up_queries`. Each follow-up query is sent as a new task to the `web_research` node.

6.  **`finalize_answer` (Node):**
    -   Receives the final set of `web_research_result` and `sources_gathered`.
    -   Uses a Gemini model (`configurable.reasoning_model`) to synthesize a coherent answer based on the research topic and summaries.
    -   Replaces short URLs in the generated answer with their original, full URLs.
    -   Filters `sources_gathered` to include only those actually cited in the final answer.
    -   Outputs an `OverallState` with the final `AIMessage` (the answer) and the `sources_gathered`.

**Graph Compilation:**

-   The nodes and edges are compiled into a `StateGraph` named "pro-search-agent".
-   The process starts at `generate_query`.
-   The graph can loop between `web_research` and `reflection` until the research is deemed sufficient or the maximum loop count is reached.
-   The process ends at `finalize_answer`.

## Frontend Components and Data Flow (`frontend/src/App.tsx`)

The frontend is a React application that interacts with the backend agent.

**Main Component: `App.tsx`**

-   **State Management:**
    -   `processedEventsTimeline`: Stores an array of `ProcessedEvent` objects, representing the activities of the backend agent (e.g., generating queries, web research, reflection).
    -   `historicalActivities`: Stores a record of `processedEventsTimeline` for each completed AI message, allowing users to see the research steps for past answers.
    -   `scrollAreaRef`: Used to auto-scroll the chat view.
    -   `hasFinalizeEventOccurredRef`: Tracks if the `finalize_answer` event has occurred to correctly associate activities with the final AI message.

-   **`useStream` Hook:**
    -   Manages the communication with the backend LangGraph agent via the `@langchain/langgraph-sdk/react` library.
    -   `apiUrl`: Configured based on development (`http://localhost:2024`) or production (`http://localhost:8123`) environment.
    -   `assistantId`: Set to "agent".
    -   `messagesKey`: Specifies that the "messages" field in the stream contains the chat messages.
    -   `onFinish`: Callback for when the stream finishes.
    -   `onUpdateEvent`: Callback for processing events from the backend agent. This is where `processedEventsTimeline` is populated based on events like `generate_query`, `web_research`, `reflection`, and `finalize_answer`.

-   **Event Processing (`onUpdateEvent`):**
    -   Transforms backend events into user-friendly `ProcessedEvent` objects with a `title` and `data` description.
    -   For `generate_query`: Shows "Generating Search Queries" and the list of queries.
    -   For `web_research`: Shows "Web Research", the number of sources gathered, and example labels.
    -   For `reflection`: Shows "Reflection" and whether the search was successful or if more information is needed (including follow-up queries).
    -   For `finalize_answer`: Shows "Finalizing Answer". Sets `hasFinalizeEventOccurredRef.current` to true.

-   **Effect Hooks (`useEffect`):**
    -   Auto-scrolls the chat area when new messages arrive.
    -   When a `finalize_answer` event has occurred and the stream is no longer loading, it associates the current `processedEventsTimeline` with the last AI message ID in `historicalActivities`. This allows the UI to display the specific research steps taken for that particular answer.

-   **`handleSubmit` Function:**
    -   Called when the user submits a new message.
    -   Clears the `processedEventsTimeline` and resets `hasFinalizeEventOccurredRef`.
    -   Converts a user-selected "effort" level (low, medium, high) into `initial_search_query_count` and `max_research_loops` for the backend.
    -   Appends the new human message to the existing messages.
    -   Calls `thread.submit()` to send the updated messages and configuration parameters to the backend agent.

-   **`handleCancel` Function:**
    -   Calls `thread.stop()` to interrupt the backend agent.
    -   Reloads the page.

-   **Rendering Logic:**
    -   If there are no messages, it displays the `WelcomeScreen` component, which allows the user to input their first query, select effort level, and model.
    -   If there are messages, it displays the `ChatMessagesView` component, which shows the conversation history, the live activity timeline for the current query, and allows access to historical activities for previous AI responses.

**Components:**

-   **`WelcomeScreen`:** The initial screen for users to start a conversation.
-   **`ChatMessagesView`:** Displays the chat messages, current agent activity, and provides input for new messages.
-   **`ActivityTimeline` (`ProcessedEvent` type):** Likely a component (not fully detailed in `App.tsx` but implied by `ProcessedEvent`) to display the sequence of agent actions.

**Data Flow Summary:**

1.  User submits a query, effort level, and model choice through `WelcomeScreen` or `ChatMessagesView`.
2.  `handleSubmit` in `App.tsx` sends this information to the backend agent via `thread.submit()`.
3.  The backend agent streams events (`generate_query`, `web_research`, etc.) back to the frontend.
4.  `onUpdateEvent` in `App.tsx` processes these events and updates `processedEventsTimeline`.
5.  The `ChatMessagesView` displays the messages from `thread.messages` and the `liveActivityEvents` (current timeline).
6.  When the agent finishes (`finalize_answer` event and `isLoading` is false), the `processedEventsTimeline` is saved to `historicalActivities` associated with the AI's response ID.

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

The backend server (when run with `langgraph dev`) also provides a LangGraph UI.
The `apiUrl` in `frontend/src/App.tsx` is set to `http://localhost:2024` for development and `http://localhost:8123` for the Docker Compose production setup.

## Leveraging the Codebase

This codebase provides a solid foundation for building advanced research and conversational AI applications. Here are some potential use cases, extensions, and improvements:

-   **Integrate New Data Sources or Tools:**
    -   Modify the `web_research` node or add new nodes to incorporate information from various sources like PDF documents, CSV files, or proprietary databases.
    -   Integrate specialized APIs (e.g., financial data APIs, scientific databases) to provide the agent with access to structured information.
    -   Add tools for document parsing (e.g., PDF readers) and data extraction.

-   **Customize Agent Behavior for Specific Tasks:**
    -   Tailor the prompts in `backend/src/agent/prompts.py` to specialize the agent for specific domains like legal research, medical information gathering (with appropriate disclaimers and safeguards), or technical troubleshooting.
    -   Adjust the `Reflection` logic to better suit the requirements of different tasks, for example, by changing how `is_sufficient` is determined or what constitutes a `knowledge_gap`.
    -   Develop new nodes or modify existing ones to perform task-specific actions (e.g., summarizing legal documents, cross-referencing medical symptoms).

-   **Enhance Frontend Features:**
    -   Implement user accounts to save chat history and preferences.
    -   Add functionality to export or share research results.
    -   Improve the visualization of sources and citations.
    -   Allow users to provide feedback on the agent's responses to help refine its performance.
    -   Develop more sophisticated ways to manage and view `historicalActivities`.

-   **Use Agent as a Backend for Other Applications:**
    -   Expose the agent's capabilities through a more robust API that can be consumed by other applications, such as custom chatbots, voice assistants, or automated reporting tools.
    -   Integrate the agent into existing workflows to provide research and information retrieval support.

-   **Improve Agent's Reasoning Capabilities:**
    -   Experiment with different Large Language Models (LLMs) available through LangChain and Google Generative AI for various nodes (query generation, reflection, answer synthesis) to find the best fit for specific needs.
    -   Explore fine-tuning models on domain-specific datasets to improve the agent's understanding and performance on specialized topics.
    -   Implement more advanced reflection mechanisms, such as multi-step reasoning or self-correction loops.
    -   Enhance the `evaluate_research` logic to make more nuanced decisions about when to continue research or finalize an answer.
    -   Allow the agent to ask clarifying questions to the user if the initial query is ambiguous.
