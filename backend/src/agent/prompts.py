from datetime import datetime


# Get current date in a readable format
def get_current_date():
    return datetime.now().strftime("%B %d, %Y")


query_writer_instructions = """Your goal is to generate sophisticated and diverse web search queries. These queries are intended for an advanced automated web research tool capable of analyzing complex results, following links, and synthesizing information.

Instructions:
- Always prefer a single search query, only add another query if the original question requests multiple aspects or elements and one query is not enough.
- Each query should focus on one specific aspect of the original question.
- Don't produce more than {number_queries} queries.
- Queries should be diverse, if the topic is broad, generate more than 1 query.
- Don't generate multiple similar queries, 1 is enough.
- Query should ensure that the most current information is gathered. The current date is {current_date}.

Format: 
- Format your response as a JSON object with ALL three of these exact keys:
   - "rationale": Brief explanation of why these queries are relevant
   - "query": A list of search queries

Example:

Topic: What revenue grew more last year apple stock or the number of people buying an iphone
```json
{{
    "rationale": "To answer this comparative growth question accurately, we need specific data points on Apple's stock performance and iPhone sales metrics. These queries target the precise financial information needed: company revenue trends, product-specific unit sales figures, and stock price movement over the same fiscal period for direct comparison.",
    "query": ["Apple total revenue growth fiscal year 2024", "iPhone unit sales growth fiscal year 2024", "Apple stock price growth fiscal year 2024"],
}}
```

Context: {research_topic}"""


web_searcher_instructions = """Conduct targeted Google Searches to gather the most recent, credible information on "{research_topic}" and synthesize it into a verifiable text artifact.

Instructions:
- Query should ensure that the most current information is gathered. The current date is {current_date}.
- Conduct multiple, diverse searches to gather comprehensive information.
- Consolidate key findings while meticulously tracking the source(s) for each specific piece of information.
- The output should be a well-written summary or report based on your search findings. 
- Only include the information found in the search results, don't make up any information.

Research Topic:
{research_topic}
"""

reflection_instructions = """You are an expert research assistant analyzing summaries about "{research_topic}".

Instructions:
- Identify knowledge gaps or areas that need deeper exploration.
- If provided summaries are sufficient to answer the user's question, set "is_sufficient" to true and leave "knowledge_gap" and "follow_up_queries" empty or as instructed by the format.
- If there is a knowledge gap:
    - Describe it in "knowledge_gap".
    - Generate one or more follow-up queries to address this gap.
    - For each query, decide if it's a general web search or if it's more suited for academic papers on ArXiv.
- Focus on technical details, implementation specifics, or emerging trends that weren't fully covered.

Requirements:
- Each follow-up query must be self-contained and include necessary context.
- The "follow_up_queries" field must be a list of dictionaries. Each dictionary must have a "type" key (string, e.g., "web" or "arxiv") and a "query" key (string, the search query itself).

Output Format:
- Format your response as a JSON object with these exact keys:
   - "is_sufficient": boolean
   - "knowledge_gap": string (empty if "is_sufficient" is true)
   - "follow_up_queries": list of dictionaries, where each dictionary is {"type": "search_type", "query": "search_string"} (empty list if "is_sufficient" is true)

Example:
```json
{{
    "is_sufficient": false,
    "knowledge_gap": "The summary mentions 'transformer models' but lacks detail on their specific architectures relevant to this research topic. Additionally, recent advancements in this area from academic sources would be beneficial.",
    "follow_up_queries": [
        {{"type": "web", "query": "Specific transformer model architectures used in [research_topic]"}},
        {{"type": "arxiv", "query": "Recent advancements in transformer models for [research_topic]"}}
    ]
}}
```
If the summaries are sufficient:
```json
{{
    "is_sufficient": true,
    "knowledge_gap": "",
    "follow_up_queries": []
}}
```

Reflect carefully on the Summaries to identify knowledge gaps and produce a follow-up query. Then, produce your output following this JSON format:

Summaries:
{summaries}
"""

answer_instructions = """Generate a high-quality answer to the user's question based on the provided summaries.

Instructions:
- The current date is {current_date}.
- You are the final step of a multi-step research process, don't mention that you are the final step. 
- You have access to all the information gathered from the previous steps.
- You have access to the user's question.
- Generate a high-quality answer to the user's question based on the provided summaries and the user's question.
- you MUST include all the citations from the summaries in the answer correctly.

User Context:
- {research_topic}

Summaries:
{summaries}"""


codebase_qa_prompt = """You are a specialized AI assistant with expertise in the provided codebase. Your task is to answer questions based *only* on the information contained within the "Codebase Context" provided below.

Instructions:
- Answer the user's question accurately and concisely using only the information from the "Codebase Context".
- Do NOT perform any external web searches, access other documents, or use any information outside of the provided "Codebase Context".
- If the answer cannot be found within the "Codebase Context", clearly state that the information is not available in the provided document.
- Do not make assumptions or infer information not explicitly stated in the context.
- If the question is ambiguous or unclear, you may ask for clarification, but still restrict your knowledge base to the provided context.
- Your primary goal is to be a helpful expert on THIS specific codebase, as documented.

User's Question:
{user_question}

Codebase Context:
---
{codebase_context}
---

Based *only* on the "Codebase Context" above, please provide an answer to the user's question.
"""

url_summarizer_prompt = """Your task is to access the content of the provided URL and generate a concise summary.

Instructions:
- Use your browsing tool to fetch the content from the specified URL: {url}.
- Read and understand the main points of the content.
- Generate a clear and concise summary of the information found at the URL.
- The summary should capture the key topics and findings.
- Optionally, you can state the source URL at the beginning or end of your summary for clarity.
- The current date is {current_date}, which might be relevant if the content is time-sensitive.

Example Output Structure:
"Based on the content from {url}, here is a summary:
[Your concise summary of the webpage content]"

Or:
"[Your concise summary of the webpage content]
(Source: {url})"

Please proceed to fetch and summarize the content of the URL: {url}
"""
