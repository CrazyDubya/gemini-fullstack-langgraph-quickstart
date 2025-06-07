import { useStream } from "@langchain/langgraph-sdk/react";
import type { Message } from "@langchain/langgraph-sdk";
import { useState, useEffect, useRef, useCallback, FormEvent } from "react";
import { ProcessedEvent } from "@/components/ActivityTimeline";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { ChatMessagesView } from "@/components/ChatMessagesView";
import { Button } from "@/components/ui/button"; // For logout button
import { Input } from "@/components/ui/input"; // For login form

const LS_USER_KEY = "geminiFullstackLangGraphUser";
const LS_CHAT_HISTORY_PREFIX = "chatHistory_";

export default function App() {
  const [currentUser, setCurrentUser] = useState<string | null>(null);
  const [usernameInput, setUsernameInput] = useState<string>("");
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [uploadedPdfInfo, setUploadedPdfInfo] = useState<{ name: string; path: string } | null>(null);

  const [processedEventsTimeline, setProcessedEventsTimeline] = useState<
    ProcessedEvent[]
  >([]);
  const [historicalActivities, setHistoricalActivities] = useState<
    Record<string, ProcessedEvent[]>
  >({});
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const hasFinalizeEventOccurredRef = useRef(false);

  // `useStream` now initializes with an empty messages array or loaded history
  // and its messages are merged with the main `chatMessages` state.
  const thread = useStream<
    {
      messages: Message[];
    initial_search_query_count: number;
    max_research_loops: number;
    reasoning_model: string;
  }>({
    apiUrl: import.meta.env.DEV
      ? "http://localhost:2024"
      : "http://localhost:8123",
    assistantId: "agent",
    messagesKey: "messages", // This key indicates where messages are in the stream's payload
    onStart: () => {
      // When a new stream starts (e.g. after submit),
      // we might not need to do anything special here if handleSubmit prepares messages.
    },
    onFinish: (event: any) => {
      console.log("Stream finished:", event);
      // Save chat history when the stream (likely an AI response cycle) finishes
      if (currentUser && thread.messages.length > 0) {
        // `thread.messages` here would be the *latest* set from the stream
        // We need to ensure we're saving the complete, concatenated history.
        // This will be handled by the useEffect watching `thread.messages`.
      }
    },
    onUpdateEvent: (event: any) => {
      let processedEvent: ProcessedEvent | null = null;
      if (event.generate_query) {
        processedEvent = {
          title: "Generating Search Queries",
          data: event.generate_query.query_list.join(", "),
        };
      } else if (event.web_research) {
        const sources = event.web_research.sources_gathered || [];
        const numSources = sources.length;
        const uniqueLabels = [
          ...new Set(sources.map((s: any) => s.label).filter(Boolean)),
        ];
        const exampleLabels = uniqueLabels.slice(0, 3).join(", ");
        processedEvent = {
          title: "Web Research",
          data: `Gathered ${numSources} sources. Related to: ${
            exampleLabels || "N/A"
          }.`,
        };
      } else if (event.reflection) {
        processedEvent = {
          title: "Reflection",
          data: event.reflection.is_sufficient
            ? "Search successful, generating final answer."
            : `Need more information, searching for ${event.reflection.follow_up_queries.join(
                ", "
              )}`,
        };
      } else if (event.finalize_answer) {
        processedEvent = {
          title: "Finalizing Answer",
          data: "Composing and presenting the final answer.",
        };
        hasFinalizeEventOccurredRef.current = true;
      }
      if (processedEvent) {
        setProcessedEventsTimeline((prevEvents) => [
          ...prevEvents,
          processedEvent!,
        ]);
      }
    },
  });

  // Effect to load user and chat history on component mount
  useEffect(() => {
    const storedUser = localStorage.getItem(LS_USER_KEY);
    if (storedUser) {
      loginUser(storedUser, true); // true to indicate it's an auto-login
    }
  }, []);

  // Effect to update chatMessages when thread.messages changes (new messages from stream)
  // and save to localStorage
  useEffect(() => {
    if (thread.messages && thread.messages.length > 0) {
      // Only update if thread.messages has new content not already in chatMessages
      // This prevents duplicating messages if thread.messages is just reflecting loaded history
      const lastThreadMessageId = thread.messages[thread.messages.length - 1]?.id;
      const lastChatMessageId = chatMessages[chatMessages.length - 1]?.id;

      if (lastThreadMessageId !== lastChatMessageId || thread.messages.length > chatMessages.length) {
         // A simple heuristic: if the last message ID is different or thread has more messages,
         // it implies new messages have arrived from the stream.
         // A more robust diffing might be needed for complex scenarios.
        setChatMessages(thread.messages);

        if (currentUser) {
          localStorage.setItem(
            `${LS_CHAT_HISTORY_PREFIX}${currentUser}`,
            JSON.stringify(thread.messages)
          );
        }
      }
    } else if (thread.messages && thread.messages.length === 0 && chatMessages.length > 0 && !thread.isLoading) {
      // This case handles when a stream is reset (e.g. after a submit) but we have existing chatMessages (history)
      // We should ensure thread.messages is also reset or aligned with chatMessages
      // This might be implicitly handled by thread.submit replacing messages.
    }

  }, [thread.messages, currentUser, chatMessages, thread.isLoading]);


  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollViewport = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]"
      );
      if (scrollViewport) {
        scrollViewport.scrollTop = scrollViewport.scrollHeight;
      }
    }
  }, [chatMessages]); // Scroll when chatMessages (combined history + live) changes

  useEffect(() => {
    if (
      hasFinalizeEventOccurredRef.current &&
      !thread.isLoading &&
      chatMessages.length > 0 // Use chatMessages here
    ) {
      const lastMessage = chatMessages[chatMessages.length - 1]; // Use chatMessages
      if (lastMessage && lastMessage.type === "ai" && lastMessage.id) {
        setHistoricalActivities((prev) => ({
          ...prev,
          [lastMessage.id!]: [...processedEventsTimeline],
        }));
      }
      hasFinalizeEventOccurredRef.current = false;
    }
  }, [chatMessages, thread.isLoading, processedEventsTimeline]);


  const loginUser = (username: string, isAutoLogin = false) => {
    if (!username.trim()) return;
    const normalizedUser = username.trim();
    setCurrentUser(normalizedUser);
    if (!isAutoLogin) { // Avoid clobbering username input during auto-login
        setUsernameInput("");
    }
    localStorage.setItem(LS_USER_KEY, normalizedUser);

    // Load chat history
    const storedHistory = localStorage.getItem(`${LS_CHAT_HISTORY_PREFIX}${normalizedUser}`);
    const history = storedHistory ? (JSON.parse(storedHistory) as Message[]) : [];
    setChatMessages(history);

    // IMPORTANT: Initialize the stream's message buffer with loaded history
    // This ensures `useStream` is aware of the historical messages from the start.
    thread.replace({ messages: history });


    // Reset timelines for the new session
    setProcessedEventsTimeline([]);
    setHistoricalActivities({});
    hasFinalizeEventOccurredRef.current = false;
  };

  const handleLoginSubmit = (e: FormEvent) => {
    e.preventDefault();
    loginUser(usernameInput);
  };

  const logoutUser = () => {
    if (currentUser) {
      // Optionally save current chat before logging out if it's not duplicative
      // The useEffect for thread.messages should handle saving, but consider edge cases.
      if (chatMessages.length > 0) {
         localStorage.setItem(`${LS_CHAT_HISTORY_PREFIX}${currentUser}`, JSON.stringify(chatMessages));
      }
    }
    setCurrentUser(null);
    localStorage.removeItem(LS_USER_KEY);
    setChatMessages([]);
    thread.replace({ messages: [] }); // Clear messages in the stream hook

    // Reset timelines
    setProcessedEventsTimeline([]);
    setHistoricalActivities({});
    hasFinalizeEventOccurredRef.current = false;
  };

  const handleSubmit = useCallback(
    (submittedInputValue: string, effort: string, model: string, selectedFile?: File) => {
      if ((!submittedInputValue.trim() && !selectedFile) || !currentUser) return;

      setProcessedEventsTimeline([]);
      hasFinalizeEventOccurredRef.current = false;

      // Handle PDF upload first if a file is selected
      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);

        fetch("/upload_pdf/", {
          method: "POST",
          body: formData,
        })
          .then((response) => {
            if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
          })
          .then((data: { name: string; path: string }) => {
            setUploadedPdfInfo(data); // Save PDF info from backend
            // Proceed to submit with text query *and* PDF info
            submitToThread(submittedInputValue, effort, model, data);
          })
          .catch((error) => {
            console.error("Error uploading file:", error);
            // Optionally: show error to user
            // Proceed to submit with text query only if PDF upload fails
            submitToThread(submittedInputValue, effort, model, null);
          });
      } else {
        // No file selected, proceed with text query only
        submitToThread(submittedInputValue, effort, model, uploadedPdfInfo);
      }
    },
    [thread, currentUser, chatMessages, uploadedPdfInfo] // Added uploadedPdfInfo
  );

  const submitToThread = useCallback(
    (textInput: string, effort: string, model: string, pdfInfo: { name: string; path: string } | null) => {
      // This function is called either directly by handleSubmit (if no file)
      // or by the fetch .then() block in handleSubmit (if file upload was successful)

      // Ensure chatMessages are up-to-date if called from async file upload
      setChatMessages(prevChatMessages => {
        const currentMessages = prevChatMessages;
        let newHumanMessageContent = textInput;
        if (pdfInfo) {
          newHumanMessageContent = textInput
            ? `${textInput} (with PDF: ${pdfInfo.name})`
            : `Processing PDF: ${pdfInfo.name}`;
        }

        const newHumanMessage: Message = {
          type: "human",
          content: newHumanMessageContent,
          id: Date.now().toString(),
        };

        const newMessages: Message[] = [...currentMessages, newHumanMessage];

        let initial_search_query_count = 0;
        let max_research_loops = 0;
        switch (effort) {
          case "low": initial_search_query_count = 1; max_research_loops = 1; break;
          case "medium": initial_search_query_count = 3; max_research_loops = 3; break;
          case "high": initial_search_query_count = 5; max_research_loops = 10; break;
        }

        thread.submit({
          messages: newMessages,
          initial_search_query_count,
          max_research_loops,
          reasoning_model: model,
          // Include PDF info if available
          uploaded_pdf_info: pdfInfo ? [pdfInfo] : null,
        });

        // Reset uploadedPdfInfo on the frontend after submission
        // so it's not re-sent with the next unrelated query.
        // If it was just uploaded now (pdfInfo is not null), then setUploadedPdfInfo(null)
        // If it was from a previous selection and now submitted (pdfInfo is from uploadedPdfInfo state), also clear.
        if (pdfInfo) { // This implies a PDF was part of this submission cycle
          setUploadedPdfInfo(null);
        }
        return newMessages; // Return newMessages for setChatMessages
      });
    },
    [thread, currentUser] // Removed chatMessages, setChatMessages updater form handles it
  );

  const handleCancel = useCallback(() => {
    thread.stop();
    // Consider if reload is the best UX, or just clearing current input/stream.
    // For now, keeping reload as it resets state cleanly.
    window.location.reload();
  }, [thread]);

  if (!currentUser) {
    return (
      <div className="flex h-screen bg-neutral-800 text-neutral-100 font-sans antialiased items-center justify-center">
        <form onSubmit={handleLoginSubmit} className="p-6 bg-neutral-700 rounded-lg shadow-xl w-full max-w-sm">
          <h2 className="text-2xl font-semibold mb-4 text-center">Login</h2>
          <Input
            type="text"
            value={usernameInput}
            onChange={(e) => setUsernameInput(e.target.value)}
            placeholder="Enter username"
            className="w-full p-2 border rounded bg-neutral-600 border-neutral-500 placeholder-neutral-400"
            required
          />
          <Button type="submit" className="w-full mt-4 bg-sky-600 hover:bg-sky-700">
            Login
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-neutral-800 text-neutral-100 font-sans antialiased">
      <main className="flex-1 flex flex-col overflow-hidden max-w-4xl mx-auto w-full">
        <header className="p-4 border-b border-neutral-700 flex justify-between items-center">
          <span className="text-sm">Logged in as: <strong className="font-semibold">{currentUser}</strong></span>
          <Button onClick={logoutUser} variant="outline" size="sm" className="border-neutral-500 hover:bg-neutral-700">
            Logout
          </Button>
        </header>
        <div
          className={`flex-1 overflow-y-auto ${
            chatMessages.length === 0 ? "flex" : "" // Use chatMessages for this condition
          }`}
        >
          {chatMessages.length === 0 && !thread.isLoading ? ( // And not loading, to show WelcomeScreen initially
            <WelcomeScreen
              handleSubmit={handleSubmit}
              isLoading={thread.isLoading}
              handleSubmit={handleSubmit} // Pass the new handleSubmit
              isLoading={thread.isLoading}
              onCancel={handleCancel}
              uploadedFileName={uploadedPdfInfo?.name} // Pass PDF name to WelcomeScreen
              clearUploadedFile={() => setUploadedPdfInfo(null)} // Allow clearing
            />
          ) : (
            <ChatMessagesView
              messages={chatMessages}
              isLoading={thread.isLoading}
              scrollAreaRef={scrollAreaRef}
              onSubmit={handleSubmit} // Pass the new handleSubmit
              onCancel={handleCancel}
              liveActivityEvents={processedEventsTimeline}
              historicalActivities={historicalActivities}
              uploadedFileName={uploadedPdfInfo?.name} // Pass PDF name to ChatMessagesView
              clearUploadedFile={() => setUploadedPdfInfo(null)} // Allow clearing
            />
          )}
        </div>
      </main>
    </div>
  );
}
