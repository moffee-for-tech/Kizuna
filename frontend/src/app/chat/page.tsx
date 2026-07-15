"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";
import { DEPARTMENT_THEMES } from "@/lib/themes";
import {
  sendMessage,
  streamMessage,
  confirmAction,
  getSessions,
  getSession,
  deleteSession,
  getPromptTemplates,
  uploadFile,
  getConnectors,
  getConnectorAuthUrl,
  getConnectorStatus,
  disconnectConnector,
  getSkills,
  type PendingAction,
  type StructuredResponse,
  type StructuredSection,
} from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { TwoFactorSettings } from "@/lib/two-factor-settings";

interface Message {
  id: string;
  role: string;
  content: string;
  timestamp?: string;
  attachment?: string;
  structured?: StructuredResponse;
  pendingAction?: PendingAction;          // unresolved permission card
  confirmationOutcome?: "approved" | "denied" | "failed";
  confirmationError?: string;
}
interface Session { id: string; title: string; department: string; message_count: number; updated_at: string }
interface Connector { id: string; name: string; description: string; connected: boolean }
interface Attachment { name: string; text: string; wordCount: number }

const MAX_UPLOAD_SIZE = 10 * 1024 * 1024; // 10MB

export default function ChatPage() {
  const { user, token, loading, logout } = useAuth();
  const router = useRouter();

  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingIndex, setStreamingIndex] = useState<number | null>(null);
  const [templates, setTemplates] = useState<string[]>([]);
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [showSessionsPanel, setShowSessionsPanel] = useState(false);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [showConnectorsModal, setShowConnectorsModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [connectingToolkit, setConnectingToolkit] = useState<string | null>(null);
  const [skills, setSkills] = useState<Array<{ id: string; name: string; description: string }>>([]);
  const [activeSkill, setActiveSkill] = useState<string | null>(null);
  const [lazySeniorMode, setLazySeniorMode] = useState<string>("full");
  const [uploadError, setUploadError] = useState<string | null>(null);
  
  interface SlashCommand {
    name: string;
    description: string;
    value: string;
  }

  const ROOT_COMMANDS: SlashCommand[] = [
    { name: "/lazy-senior ...", description: "Configure or execute Lazy Senior developer commands", value: "lazy-senior" }
  ];

  const LAZY_SENIOR_COMMANDS: SlashCommand[] = [
    { name: "/lazy-senior lite", description: "Lite Mode (standard-library-first)", value: "/lazy-senior lite" },
    { name: "/lazy-senior full", description: "Full Mode (aggressive simplification)", value: "/lazy-senior full" },
    { name: "/lazy-senior ultra", description: "Ultra Mode (extreme deletion of code)", value: "/lazy-senior ultra" },
    { name: "/lazy-senior off", description: "Deactivate Lazy Senior mode", value: "/lazy-senior off" },
    { name: "/lazy-senior-review", description: "Review workspace changes for over-engineering", value: "/lazy-senior-review" },
    { name: "/lazy-senior-audit", description: "Audit whole workspace for design bloat", value: "/lazy-senior-audit" },
    { name: "/lazy-senior-debt", description: "Build technical debt ledger", value: "/lazy-senior-debt" },
    { name: "/lazy-senior-gain", description: "Show scoreboard & impact benchmark", value: "/lazy-senior-gain" },
    { name: "/lazy-senior-help", description: "Show reference card & help", value: "/lazy-senior-help" },
  ];

  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashMenuIndex, setSlashMenuIndex] = useState(0);
  const [slashMenuLevel, setSlashMenuLevel] = useState<"root" | "lazy-senior">("root");
  const [filteredSlashCommands, setFilteredSlashCommands] = useState<SlashCommand[]>(ROOT_COMMANDS);

  const selectSlashCommand = (cmd: SlashCommand) => {
    if (cmd.value === "lazy-senior") {
      setInput("/lazy-senior ");
      setSlashMenuLevel("lazy-senior");
      setFilteredSlashCommands(LAZY_SENIOR_COMMANDS);
      setSlashMenuIndex(0);
      setShowSlashMenu(true);
      if (inputRef.current) {
        inputRef.current.focus();
      }
    } else {
      setInput(cmd.value);
      setShowSlashMenu(false);
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }
  };

  const handleInputChange = (val: string) => {
    setInput(val);
    if (val === "/" || val.startsWith("/")) {
      const query = val.toLowerCase();
      if (query.startsWith("/lazy-senior") && query !== "/lazy-senior") {
        setSlashMenuLevel("lazy-senior");
        const filtered = LAZY_SENIOR_COMMANDS.filter(cmd => cmd.value.toLowerCase().startsWith(query));
        setFilteredSlashCommands(filtered);
        setShowSlashMenu(filtered.length > 0);
      } else if (query === "/lazy-senior") {
        setSlashMenuLevel("lazy-senior");
        setFilteredSlashCommands(LAZY_SENIOR_COMMANDS);
        setShowSlashMenu(true);
      } else {
        setSlashMenuLevel("root");
        const filtered = ROOT_COMMANDS.filter(cmd => cmd.name.toLowerCase().startsWith(query));
        setFilteredSlashCommands(filtered);
        setShowSlashMenu(filtered.length > 0);
      }
      setSlashMenuIndex(0);
    } else {
      setShowSlashMenu(false);
    }
  };

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const msgKeyCounter = useRef(0);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isFirstLoad = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleStop = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  // Per-message edit buffer: messageId → (actionIndex → (arg_key → new value))
  // actionIndex is "single" for direct destructive tools, otherwise the
  // stringified sub-tool index inside a MULTI_EXECUTE batch.
  const [editBuffer, setEditBuffer] = useState<Record<string, Record<string, Record<string, string>>>>({});

  const updateEdit = useCallback((messageId: string, actionIdx: string, argKey: string, value: string) => {
    setEditBuffer((prev) => {
      const msgEdits = prev[messageId] || {};
      const actionEdits = msgEdits[actionIdx] || {};
      return {
        ...prev,
        [messageId]: {
          ...msgEdits,
          [actionIdx]: { ...actionEdits, [argKey]: value },
        },
      };
    });
  }, []);

  const buildOverridesPayload = useCallback((messageId: string, isBatch: boolean): Record<string, unknown> | undefined => {
    const msgEdits = editBuffer[messageId];
    if (!msgEdits) return undefined;
    if (isBatch) {
      // Already keyed by index strings — pass through as-is
      return msgEdits as Record<string, unknown>;
    }
    // Single action: flatten the "single" bucket so the backend sees
    // {arg_key: value} at the top level.
    return msgEdits["single"] as Record<string, unknown> | undefined;
  }, [editBuffer]);

  const handleConfirmAction = useCallback(async (messageId: string, actionId: string, approved: boolean, isBatch: boolean) => {
    // Optimistic: lock buttons by marking outcome
    setMessages((prev) => {
      const u = [...prev];
      const idx = u.findIndex((m) => m.id === messageId);
      if (idx >= 0) u[idx] = { ...u[idx], confirmationOutcome: approved ? "approved" : "denied" };
      return u;
    });
    try {
      const overrides = approved ? buildOverridesPayload(messageId, isBatch) : undefined;
      const resp = await confirmAction(actionId, approved, overrides);
      setMessages((prev) => {
        const u = [...prev];
        const idx = u.findIndex((m) => m.id === messageId);
        if (idx >= 0) {
          u[idx] = {
            ...u[idx],
            pendingAction: undefined,
            structured: resp.structured,
          };
        }
        return u;
      });
      setEditBuffer((prev) => {
        const next = { ...prev };
        delete next[messageId];
        return next;
      });
    } catch (err: any) {
      setMessages((prev) => {
        const u = [...prev];
        const idx = u.findIndex((m) => m.id === messageId);
        if (idx >= 0) {
          u[idx] = {
            ...u[idx],
            confirmationOutcome: "failed",
            confirmationError: err?.message || "Confirmation failed",
          };
        }
        return u;
      });
    }
  }, []);

  const nextMsgId = () => `msg-${++msgKeyCounter.current}`;
  const theme = user ? DEPARTMENT_THEMES[user.department] || DEPARTMENT_THEMES.admin : DEPARTMENT_THEMES.admin;
  useEffect(() => { if (!loading && !user) router.push("/"); }, [user, loading, router]);
  useEffect(() => { if (token) { loadSessions(); loadTemplates(); loadConnectors(); loadSkills(); } }, [token]);

  // Scroll to bottom only for new messages, not when loading old sessions
  useEffect(() => {
    if (isFirstLoad.current) {
      isFirstLoad.current = false;
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  // Escape key to close modal
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showConnectorsModal) setShowConnectorsModal(false);
        if (showSettingsModal) setShowSettingsModal(false);
      }
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [showConnectorsModal, showSettingsModal]);

  const loadSessions = async () => { try { setSessions(await getSessions()); } catch (err) { console.error("Failed to load sessions:", err); } };
  const loadTemplates = async () => { try { const d = await getPromptTemplates(); setTemplates(d.templates || []); } catch (err) { console.error("Failed to load templates:", err); } };
  const loadConnectors = async () => { try { const d = await getConnectors(); setConnectors(d.connectors || []); } catch (err) { console.error("Failed to load connectors:", err); } };
  const loadSkills = async () => { try { const d = await getSkills(); setSkills(d.skills || []); } catch (err) { console.error("Failed to load skills:", err); } };

  const cleanupPolling = () => {
    if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null; }
    if (pollTimeoutRef.current) { clearTimeout(pollTimeoutRef.current); pollTimeoutRef.current = null; }
  };

  const handleToggleConnector = async (c: Connector) => {
    if (c.connected) {
      try {
        await disconnectConnector(c.id);
        loadConnectors();
      } catch (err) {
        console.error("Disconnect failed:", err);
      }
      return;
    }
    // Initiate OAuth
    cleanupPolling();
    setConnectingToolkit(c.id);
    try {
      const { auth_url } = await getConnectorAuthUrl(c.id);
      window.open(auth_url, "_blank");

      // Poll for connection status until ACTIVE or timeout
      pollIntervalRef.current = setInterval(async () => {
        try {
          const { status } = await getConnectorStatus(c.id);
          if (status === "ACTIVE") {
            cleanupPolling();
            setConnectingToolkit(null);
            loadConnectors();
          }
        } catch (err) {
          console.error("Connector status check failed:", err);
        }
      }, 2000);

      // Timeout after 2 minutes
      pollTimeoutRef.current = setTimeout(() => {
        cleanupPolling();
        setConnectingToolkit(null);
      }, 120000);
    } catch (err) {
      console.error("Auth failed:", err);
      setConnectingToolkit(null);
    }
  };

  const loadSession = async (sessionId: string) => {
    isFirstLoad.current = true;
    try {
      const d = await getSession(sessionId);
      setActiveSessionId(sessionId);
      setMessages((d.messages || []).map((m: any) => ({ ...m, id: m.id || nextMsgId() })));
      setActiveSkill(d.active_skill || null);
      setLazySeniorMode(d.lazy_senior_mode || "full");
      setShowSessionsPanel(false);
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  };

  const handleNewChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    setActiveSkill(null);
    setLazySeniorMode("full");
    setShowSessionsPanel(false);
    inputRef.current?.focus();
  };

  const handleDeleteSession = async (sessionId: string) => {
    try { await deleteSession(sessionId); if (activeSessionId === sessionId) handleNewChat(); loadSessions(); } catch (err) { console.error("Failed to delete session:", err); }
  };

  const handleSend = useCallback(async () => {
    if (!(input || "").trim() || isStreaming) return;
    const userMessage = (input || "").trim();
    const currentAttachment = attachment;
    setInput("");
    setAttachment(null);
    setIsStreaming(true);
    isFirstLoad.current = false;

    // Sync lazy senior mode locally if user typed /lazy-senior [mode]
    if (userMessage.toLowerCase().startsWith("/lazy-senior")) {
      const parts = userMessage.split(/\s+/);
      if (parts.length > 1) {
        const mode = parts[1].trim().toLowerCase();
        if (mode === "off") {
          setActiveSkill(null);
        } else if (["lite", "full", "ultra"].includes(mode)) {
          setActiveSkill("lazy-senior");
          setLazySeniorMode(mode);
        }
      } else {
        setActiveSkill("lazy-senior");
        setLazySeniorMode("full");
      }
    }

    const displayMessage = currentAttachment ? `${userMessage}` : userMessage;
    setMessages((prev) => {
      const newMessages = [...prev, { id: nextMsgId(), role: "user", content: displayMessage, attachment: currentAttachment?.name }];
      setStreamingIndex(newMessages.length);
      return [...newMessages, { id: nextMsgId(), role: "assistant", content: "" }];
    });

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await streamMessage(
        userMessage,
        activeSessionId || undefined,
        currentAttachment?.text,
        currentAttachment?.name,
        controller.signal,
        activeSkill || undefined,
        lazySeniorMode
      );
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No reader");

      let newSessionId = activeSessionId;
      let structuredData: StructuredResponse | null = null;
      const liveToolCalls: Array<{ name: string; raw_name: string; status: "running" | "success" | "failed" }> = [];
      let buffer = "";
      let currentEvent = "";

      // Helper: update the assistant message with live tool calls
      const renderToolCalls = () => {
        const snapshot = liveToolCalls.map((t) => ({ ...t }));
        setMessages((prev) => {
          const u = [...prev];
          const last = u[u.length - 1];
          if (last && last.role === "assistant") {
            u[u.length - 1] = {
              ...last,
              structured: {
                title: last.structured?.title || "",
                summary: last.structured?.summary || "",
                sections: last.structured?.sections || [],
                key_takeaways: last.structured?.key_takeaways || [],
                tool_calls: snapshot,
              },
            };
          }
          return u;
        });
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
            continue;
          }
          if (line.startsWith("data:")) {
            const data = line.slice(5).trim();
            if (!data) continue;
            try {
              const parsed = JSON.parse(data);

              if (currentEvent === "session") {
                if (parsed.session_id) newSessionId = parsed.session_id;
              } else if (currentEvent === "tool_start") {
                liveToolCalls.push({
                  name: parsed.name,
                  raw_name: parsed.raw_name,
                  status: "running",
                });
                renderToolCalls();
              } else if (currentEvent === "tool_end") {
                const existing = liveToolCalls.find((t) => t.raw_name === parsed.raw_name && t.status === "running");
                if (existing) existing.status = parsed.status || "success";
                renderToolCalls();
              } else if (currentEvent === "confirmation_required") {
                // Backend gated a destructive tool. Attach pending action to
                // the in-flight assistant bubble so the card can render.
                const pa: PendingAction = parsed;
                setMessages((prev) => {
                  const u = [...prev];
                  const last = u[u.length - 1];
                  if (last && last.role === "assistant") {
                    u[u.length - 1] = { ...last, pendingAction: pa };
                  }
                  return u;
                });
                continue;
              } else if (currentEvent === "structured" || parsed.title !== undefined) {
                structuredData = {
                  title: parsed.title || "",
                  summary: parsed.summary || "",
                  sections: Array.isArray(parsed.sections) ? parsed.sections : [],
                  key_takeaways: Array.isArray(parsed.key_takeaways) ? parsed.key_takeaways : [],
                  tool_calls: Array.isArray(parsed.tool_calls) ? parsed.tool_calls : liveToolCalls,
                };
              } else if (parsed.session_id && !parsed.title) {
                newSessionId = parsed.session_id;
              }
            } catch (err) {
              console.error("Failed to parse stream data:", err);
            }
          } else if (line.trim() === "") {
            // Blank line signals end of SSE event — reset event type
            currentEvent = "";
          }
        }
      }

      if (structuredData) {
        // Animate sections appearing one by one
        const sr = structuredData;
        const totalSections = sr.sections.length;

        // Show title + summary first
        setMessages((prev) => {
          const u = [...prev];
          u[u.length - 1] = {
            ...u[u.length - 1],
            content: "",
            structured: { ...sr, sections: [], key_takeaways: [] },
          };
          return u;
        });
        await new Promise((r) => setTimeout(r, 150));

        // Reveal sections one by one
        for (let i = 0; i < totalSections; i++) {
          setMessages((prev) => {
            const u = [...prev];
            const current = u[u.length - 1].structured!;
            u[u.length - 1] = {
              ...u[u.length - 1],
              content: "",
              structured: { ...current, sections: sr.sections.slice(0, i + 1) },
            };
            return u;
          });
          await new Promise((r) => setTimeout(r, 120));
        }

        // Reveal key takeaways
        if (sr.key_takeaways.length > 0) {
          setMessages((prev) => {
            const u = [...prev];
            u[u.length - 1] = {
              ...u[u.length - 1],
              content: "",
              structured: sr,
            };
            return u;
          });
        }
      }

      if (newSessionId) setActiveSessionId(newSessionId);
      loadSessions();
    } catch (streamErr: any) {
      // User pressed Stop — don't fall back to non-streaming, just mark partial as stopped
      if (streamErr?.name === "AbortError" || controller.signal.aborted) {
        setMessages((prev) => {
          const u = [...prev];
          const last = u[u.length - 1];
          if (last && last.role === "assistant") {
            const hadContent = !!(last.content || (last.structured && (last.structured.sections.length > 0 || (last.structured.tool_calls?.length ?? 0) > 0)));
            u[u.length - 1] = {
              ...last,
              content: (last.content || "") + (hadContent ? "\n\n_(stopped by user)_" : "_(stopped by user)_"),
            };
          }
          return u;
        });
      } else {
      try {
        const data = await sendMessage(
          userMessage,
          activeSessionId || undefined,
          currentAttachment?.text,
          currentAttachment?.name,
          activeSkill || undefined,
          lazySeniorMode
        );
        setMessages((prev) => {
          const u = [...prev];
          if (u[u.length - 1]?.role === "assistant" && !u[u.length - 1]?.content && !u[u.length - 1]?.structured) u.pop();
          u.push({ id: nextMsgId(), role: "assistant", content: "", structured: data.structured });
          return u;
        });
        if (data.session_id) setActiveSessionId(data.session_id);
        loadSessions();
      } catch (e: any) {
        console.error("Chat failed:", e);
        setMessages((prev) => {
          const u = [...prev];
          const errorMsg = "Something went wrong. Please try again.";
          if (u[u.length - 1]?.role === "assistant" && !u[u.length - 1]?.content) {
            u[u.length - 1].content = errorMsg;
          } else {
            u.push({ id: nextMsgId(), role: "assistant", content: errorMsg });
          }
          return u;
        });
      }
      }
    } finally {
      setIsStreaming(false);
      setStreamingIndex(null);
      abortControllerRef.current = null;
    }
  }, [input, isStreaming, activeSessionId, attachment]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSlashMenu) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashMenuIndex(prev => (prev + 1) % filteredSlashCommands.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashMenuIndex(prev => (prev - 1 + filteredSlashCommands.length) % filteredSlashCommands.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        if (filteredSlashCommands[slashMenuIndex]) {
          selectSlashCommand(filteredSlashCommands[slashMenuIndex]);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setShowSlashMenu(false);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    if (file.size > MAX_UPLOAD_SIZE) {
      setUploadError("File too large. Max 10MB.");
      e.target.value = "";
      return;
    }
    try {
      const d = await uploadFile(file);
      setAttachment({ name: d.filename, text: d.text, wordCount: d.word_count });
      inputRef.current?.focus();
    } catch (err) {
      console.error("Upload failed:", err);
      setUploadError("Upload failed. Please try again.");
    }
    e.target.value = "";
  };


  if (loading || !user) return <div className="flex items-center justify-center min-h-screen"><div className="text-[#a8a49d]">Loading...</div></div>;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Icon Sidebar */}
      <div className="w-[52px] flex-shrink-0 bg-[#2a2a27] border-r border-[#3e3e38] flex flex-col items-center py-3 gap-1">
        {/* Toggle sessions panel */}
        <button onClick={() => setShowSessionsPanel(!showSessionsPanel)} className="w-9 h-9 rounded-lg flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] hover:bg-[#3a3a36] transition-colors" title="Toggle sidebar" aria-label="Toggle sidebar" aria-pressed={showSessionsPanel}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
        </button>

        {/* New chat */}
        <button onClick={handleNewChat} className="w-9 h-9 rounded-lg flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] hover:bg-[#3a3a36] transition-colors" title="New chat" aria-label="New chat">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </button>

        {/* Sessions */}
        <button onClick={() => setShowSessionsPanel(!showSessionsPanel)} className="w-9 h-9 rounded-lg flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] hover:bg-[#3a3a36] transition-colors" title="Conversations" aria-label="Conversations">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        </button>

        {/* Connectors */}
        <button onClick={() => setShowConnectorsModal(true)} className="w-9 h-9 rounded-lg flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] hover:bg-[#3a3a36] transition-colors" title="Connectors" aria-label="Connectors">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        </button>

        {/* Templates */}
        <button onClick={() => { if (templates.length > 0) { setInput(templates[Math.floor(Math.random() * templates.length)]); inputRef.current?.focus(); } }} className="w-9 h-9 rounded-lg flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] hover:bg-[#3a3a36] transition-colors" title="Random template" aria-label="Random template">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
        </button>

        <div className="flex-1" />

        {/* Settings (2FA) */}
        <button onClick={() => setShowSettingsModal(true)} className="w-9 h-9 rounded-lg flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] hover:bg-[#3a3a36] transition-colors" title="Settings" aria-label="Settings">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
        </button>

        {/* User avatar + logout */}
        <button onClick={() => { logout(); router.push("/"); }} className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-semibold transition-colors" style={{ backgroundColor: theme.bgAccent, color: theme.accent }} title="Sign out" aria-label="Sign out">
          {user.name.charAt(0).toUpperCase()}
        </button>
      </div>

      {/* Sessions Panel (collapsible) */}
      {showSessionsPanel && (
        <div className="w-[260px] flex-shrink-0 bg-[#2a2a27] border-r border-[#3e3e38] flex flex-col overflow-hidden">
          {/* Branding header */}
          <div className="px-4 py-4 border-b border-[#3e3e38]">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-7 h-7 rounded-lg bg-[#e8e4dd] flex items-center justify-center p-1 flex-shrink-0">
                <span className="text-sm font-bold text-[#2a2a27]">K</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-[#e8e4dd] truncate">Kizuna AI Vault</div>
                <div className="text-[10px] text-[#7a776f] truncate">powered by Kizuna</div>
              </div>
            </div>
          </div>
          <div className="p-3 border-b border-[#3e3e38]">
            <h3 className="text-xs font-medium text-[#a8a49d] uppercase tracking-wider">Conversations</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {sessions.length === 0 && <p className="text-xs text-[#7a776f] px-2 py-4">No conversations yet</p>}
            {sessions.map((s) => (
              <div key={s.id} className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${activeSessionId === s.id ? "bg-[#3a3a36] text-[#e8e4dd]" : "text-[#a8a49d] hover:bg-[#353531] hover:text-[#e8e4dd]"}`} onClick={() => loadSession(s.id)}>
                <span className="flex-1 truncate text-xs">{s.title}</span>
                <button onClick={(e) => { e.stopPropagation(); handleDeleteSession(s.id); }} className="opacity-0 group-hover:opacity-100 text-[#7a776f] hover:text-[#f87171] transition-all">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header Bar */}
        <div className="h-[52px] border-b border-[#3e3e38] bg-[#2a2a27]/85 backdrop-blur flex items-center justify-between px-6 z-10 flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: theme.accent }} />
            <span className="text-sm font-semibold text-[#e8e4dd] capitalize">{theme.label} AI</span>
          </div>
          

        </div>
        {/* Messages or Empty State */}
        <div className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            /* Empty state — Claude.ai style centered */
            <div className="flex flex-col items-center justify-center h-full px-4">
              <div className="flex items-center gap-3 mb-8">
                <span className="text-3xl" style={{ color: theme.accent }}>*</span>
                <h1 className="text-2xl font-medium text-[#e8e4dd]">What shall we think through?</h1>
              </div>

              {/* Input box — centered like Claude.ai */}
              <div className="w-full max-w-[560px] relative">
                {showSlashMenu && (
                  <div className="absolute bottom-full left-0 right-0 mb-2 z-50 bg-[#3a3a36]/95 backdrop-blur border border-[#4a4a44] rounded-xl shadow-2xl overflow-hidden max-h-60 overflow-y-auto">
                    {slashMenuLevel === "lazy-senior" && (
                      <div className="px-4 py-2 bg-[#454540]/70 border-b border-[#4a4a44]/50 text-[10px] font-semibold text-[#a8a49d] uppercase tracking-wider flex items-center gap-1.5">
                        <span>⚡ Lazy Senior Skills</span>
                      </div>
                    )}
                      <div
                        key={cmd.name}
                        className={`px-4 py-2.5 cursor-pointer border-b border-[#454540]/50 last:border-b-0 flex flex-col transition-colors ${
                          slashMenuIndex === idx
                            ? "bg-[#454540] text-[#fbbf24]"
                            : "text-[#a8a49d] hover:bg-[#40403b]/50 hover:text-[#fbbf24]"
                        }`}
                        onClick={() => selectSlashCommand(cmd)}
                      >
                        <span className={`text-xs font-mono font-semibold ${slashMenuIndex === idx ? "text-[#fbbf24]" : "text-[#e8e4dd]"}`}>
                          {cmd.name}
                        </span>
                        <span className={`text-[10px] mt-0.5 ${slashMenuIndex === idx ? "text-[#e8e4dd]" : "text-[#7a776f]"}`}>
                          {cmd.description}
                        </span>
                      </div>
                  </div>
                )}
                <div className="bg-[#3a3a36] border border-[#4a4a44] rounded-2xl overflow-hidden">
                  {attachment && (
                    <div className="px-4 pt-3 flex items-center gap-2">
                      <div className="flex items-center gap-2 px-3 py-1.5 bg-[#454540] rounded-lg text-xs text-[#e8e4dd]">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
                        <span className="truncate max-w-[200px]">{attachment.name}</span>
                        <span className="text-[#7a776f]">{attachment.wordCount} words</span>
                        <button onClick={() => setAttachment(null)} className="text-[#7a776f] hover:text-[#e8e4dd] transition-colors">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                      </div>
                    </div>
                  )}
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => handleInputChange(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={attachment ? "Ask about this document..." : "How can I help you today?"}
                    rows={1}
                    className="w-full resize-none px-4 pt-4 pb-2 bg-transparent text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none text-sm max-h-32"
                    style={{ minHeight: "44px" }}
                  />
                  <div className="flex items-center justify-between px-3 pb-3">
                    <label className="cursor-pointer text-[#7a776f] hover:text-[#a8a49d] transition-colors p-1.5 rounded-lg hover:bg-[#454540]">
                      <input type="file" accept=".pdf,.docx,.csv,.xlsx,.txt,.md" className="hidden" onChange={handleFileUpload} />
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#7a776f]">{theme.label}</span>
                      <button
                        onClick={isStreaming ? handleStop : handleSend}
                        disabled={!isStreaming && !(input || "").trim()}
                        className="p-1.5 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#454540]"
                        title={isStreaming ? "Stop generating" : "Send"}
                        aria-label={isStreaming ? "Stop generating" : "Send message"}
                      >
                        {isStreaming ? (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" className="text-[#e8e4dd]"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#a8a49d]"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
                {uploadError && (
                  <div className="mt-2 text-[#f87171] text-xs bg-[#f8717115] px-3 py-2 rounded-lg flex items-center justify-between">
                    <span>{uploadError}</span>
                    <button onClick={() => setUploadError(null)} className="text-[#f87171] hover:text-[#e8e4dd] ml-2" aria-label="Dismiss error">&times;</button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* Messages */
            <div className="max-w-3xl mx-auto py-6 px-4 space-y-1">
              {messages.map((msg, i) => (
                <div key={msg.id} className="animate-fade-in">
                  <div className="flex items-center gap-2 mb-1.5 mt-5">
                    <span className="text-xs font-medium" style={{ color: msg.role === "assistant" ? theme.accent : "#a8a49d" }}>
                      {msg.role === "assistant" ? "Kizuna" : "You"}
                    </span>
                  </div>
                  <div className={`rounded-xl px-4 py-3 ${msg.role === "user" ? "bg-[#3a3a36] text-[#e8e4dd]" : "bg-[#353531] border border-[#3e3e38] text-[#d8d4cd]"}`}>
                    {msg.attachment && (
                      <div className="flex items-center gap-2 mb-2 px-3 py-1.5 bg-[#454540] rounded-lg text-xs text-[#e8e4dd] w-fit">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
                        <span>{msg.attachment}</span>
                      </div>
                    )}
                    {msg.role === "assistant" ? (
                      <div className={`${streamingIndex === i ? "streaming-content" : ""}`}>
                        {streamingIndex === i && !msg.structured && !msg.content ? (
                          <div className="flex items-center gap-1.5 text-sm text-[#a8a49d] py-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#a8a49d] animate-pulse-dot" />
                            <span className="w-1.5 h-1.5 rounded-full bg-[#a8a49d] animate-pulse-dot" style={{ animationDelay: "0.2s" }} />
                            <span className="w-1.5 h-1.5 rounded-full bg-[#a8a49d] animate-pulse-dot" style={{ animationDelay: "0.4s" }} />
                            <span className="ml-1">Thinking</span>
                          </div>
                        ) : msg.structured ? (
                          <div className="structured-response">
                            {/* Tool calls — show which connectors were hit */}
                            {msg.structured.tool_calls && msg.structured.tool_calls.length > 0 && (
                              <div className="mb-3 space-y-1.5">
                                {msg.structured.tool_calls.map((tc, idx) => (
                                  <div key={`tool-${idx}-${tc.raw_name}`} className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider animate-section-in" style={{ animationDelay: `${idx * 100}ms` }}>
                                    {tc.status === "running" ? (
                                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin" style={{ color: theme.accent }}><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                                    ) : tc.status === "success" ? (
                                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ color: "#4ade80" }}><polyline points="20 6 9 17 4 12"/></svg>
                                    ) : (
                                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "#f87171" }}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                                    )}
                                    <span className="text-[#a8a49d]">{tc.name}</span>
                                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[#5a574f]"><polyline points="9 18 15 12 9 6"/></svg>
                                  </div>
                                ))}
                              </div>
                            )}
                            {/* Title */}
                            {msg.structured.title && (
                              <h3 className="text-base font-semibold text-[#e8e4dd] mb-1">{msg.structured.title}</h3>
                            )}
                            {/* Summary */}
                            {msg.structured.summary && (
                              <p className="text-sm text-[#a8a49d] mb-3 italic leading-relaxed">{msg.structured.summary}</p>
                            )}
                            {/* Sections */}
                            {(msg.structured.sections || []).map((section, si) => (
                              <div key={`${section.heading}-${si}`} className="mb-3 animate-section-in" style={{ animationDelay: `${si * 80}ms` }}>
                                {section.heading && (
                                  <h4 className="text-sm font-semibold text-[#e8e4dd] mb-1.5 flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: theme.accent }} />
                                    {section.heading}
                                  </h4>
                                )}
                                <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-p:leading-relaxed pl-3.5">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{section.content}</ReactMarkdown>
                                </div>
                              </div>
                            ))}
                            {/* Key Takeaways */}
                            {msg.structured.key_takeaways && msg.structured.key_takeaways.length > 0 && (
                              <div className="mt-3 pt-3 border-t border-[#3e3e38] animate-section-in">
                                <h4 className="text-xs font-semibold uppercase tracking-wider text-[#a8a49d] mb-2">Key Takeaways</h4>
                                <ul className="space-y-1">
                                  {msg.structured.key_takeaways.map((t, ti) => (
                                    <li key={`takeaway-${ti}-${t.slice(0, 20)}`} className="flex items-start gap-2 text-sm text-[#d8d4cd]">
                                      <span className="mt-1.5 w-1 h-1 rounded-full flex-shrink-0" style={{ backgroundColor: theme.accent }} />
                                      {t}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {streamingIndex === i && <span className="streaming-cursor" />}
                          </div>
                        ) : (
                          <div className="prose prose-invert prose-sm max-w-none prose-p:my-1.5 prose-p:leading-relaxed">
                            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> }}>{msg.content || "..."}</ReactMarkdown>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                    )}
                    {/* Permission card — render when the agent gated a destructive tool */}
                    {msg.role === "assistant" && msg.pendingAction && !msg.confirmationOutcome && (
                      <div className="mt-3 border border-[#5a574f] rounded-lg bg-[#3a3a36] p-3 animate-fade-in">
                        <div className="flex items-center gap-2 mb-2">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "#fbbf24" }}>
                            <path d="M12 9v4M12 17h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                          </svg>
                          <span className="text-xs font-semibold uppercase tracking-wider text-[#fbbf24]">Permission required</span>
                        </div>
                        <p className="text-sm text-[#e8e4dd] mb-3 font-medium">{msg.pendingAction.human_description}</p>
                        {/* Editable content preview — one block per destructive action */}
                        {(msg.pendingAction.details || []).map((det, dIdx) => {
                          const isBatch = (msg.pendingAction!.details.length > 1);
                          const actionKey = isBatch ? String(dIdx) : "single";
                          const msgEdits = editBuffer[msg.id]?.[actionKey] || {};
                          return (
                            <div key={`det-${dIdx}-${det.tool_slug}`} className="mb-3 rounded-md bg-[#2f2f2c] border border-[#3e3e38] overflow-hidden">
                              {isBatch && (
                                <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-[#7a776f] bg-[#353531] border-b border-[#3e3e38]">
                                  Action {dIdx + 1} of {msg.pendingAction!.details.length} — {det.tool_slug}
                                </div>
                              )}
                              <div className="px-3 py-2 space-y-2">
                                {det.fields.map((f, fIdx) => {
                                  const currentValue = msgEdits[f.arg_key] ?? f.value;
                                  const isEdited = msgEdits[f.arg_key] !== undefined && msgEdits[f.arg_key] !== f.value;
                                  const isEditable = f.editable !== false;
                                  return (
                                    <div key={`f-${fIdx}-${f.arg_key}`} className={f.multiline ? "" : "flex gap-2 items-start"}>
                                      <div className={`text-[11px] font-semibold uppercase tracking-wider text-[#a8a49d] ${f.multiline ? "mb-1" : "min-w-[80px] mt-2"} flex items-center gap-1`}>
                                        <span>{f.label}</span>
                                        {isEdited && <span className="text-[9px] normal-case font-normal text-[#fbbf24]" title="edited">●</span>}
                                      </div>
                                      {!isEditable ? (
                                        f.multiline ? (
                                          <div className="text-xs text-[#e8e4dd] whitespace-pre-wrap font-mono bg-[#1f1f1c] border border-[#3e3e38] rounded p-2 max-h-64 overflow-y-auto flex-1">{currentValue}</div>
                                        ) : (
                                          <div className="text-xs text-[#a8a49d] break-all py-1.5 flex-1">{currentValue}</div>
                                        )
                                      ) : f.multiline ? (
                                        <textarea
                                          value={currentValue}
                                          onChange={(e) => updateEdit(msg.id, actionKey, f.arg_key, e.target.value)}
                                          className="w-full text-xs text-[#e8e4dd] font-mono bg-[#1f1f1c] border border-[#3e3e38] focus:border-[#fbbf24] rounded p-2 min-h-[64px] max-h-64 overflow-y-auto resize-y focus:outline-none"
                                          rows={Math.min(8, Math.max(3, currentValue.split("\n").length))}
                                        />
                                      ) : (
                                        <input
                                          type="text"
                                          value={currentValue}
                                          onChange={(e) => updateEdit(msg.id, actionKey, f.arg_key, e.target.value)}
                                          className="flex-1 text-xs text-[#e8e4dd] bg-[#1f1f1c] border border-[#3e3e38] focus:border-[#fbbf24] rounded px-2 py-1.5 focus:outline-none"
                                        />
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handleConfirmAction(msg.id, msg.pendingAction!.action_id, true, msg.pendingAction!.details.length > 1)}
                            className="px-3 py-1.5 rounded-md text-xs font-semibold bg-[#4ade80] text-[#1a1a17] hover:bg-[#5beb91] transition-colors"
                          >
                            Allow
                          </button>
                          <button
                            onClick={() => handleConfirmAction(msg.id, msg.pendingAction!.action_id, false, msg.pendingAction!.details.length > 1)}
                            className="px-3 py-1.5 rounded-md text-xs font-semibold bg-[#454540] text-[#e8e4dd] hover:bg-[#555550] transition-colors"
                          >
                            Deny
                          </button>
                          {editBuffer[msg.id] && Object.values(editBuffer[msg.id]).some((a) => Object.keys(a).length > 0) && (
                            <span className="text-[10px] text-[#fbbf24]">● edited</span>
                          )}
                          <span className="text-[10px] text-[#7a776f] ml-auto">expires {new Date(msg.pendingAction.expires_at).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    )}
                    {msg.confirmationOutcome === "failed" && (
                      <div className="mt-2 text-xs text-[#f87171]">Confirmation failed: {msg.confirmationError}</div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Bottom input bar (only when in conversation) */}
        {messages.length > 0 && (
          <div className="p-4 bg-[#2f2f2c]">
            <div className="max-w-3xl mx-auto relative">
              {showSlashMenu && (
                <div className="absolute bottom-full left-0 right-0 mb-2 z-50 bg-[#3a3a36]/95 backdrop-blur border border-[#4a4a44] rounded-xl shadow-2xl overflow-hidden max-h-60 overflow-y-auto">
                  {slashMenuLevel === "lazy-senior" && (
                    <div className="px-4 py-2 bg-[#454540]/70 border-b border-[#4a4a44]/50 text-[10px] font-semibold text-[#a8a49d] uppercase tracking-wider flex items-center gap-1.5">
                      <span>⚡ Lazy Senior Skills</span>
                    </div>
                  )}
                  {filteredSlashCommands.map((cmd, idx) => (
                    <div
                      key={cmd.name}
                      className={`px-4 py-2.5 cursor-pointer border-b border-[#454540]/50 last:border-b-0 flex flex-col transition-colors ${
                        slashMenuIndex === idx
                          ? "bg-[#454540] text-[#fbbf24]"
                          : "text-[#a8a49d] hover:bg-[#40403b]/50 hover:text-[#fbbf24]"
                      }`}
                      onClick={() => selectSlashCommand(cmd)}
                    >
                      <span className={`text-xs font-mono font-semibold ${slashMenuIndex === idx ? "text-[#fbbf24]" : "text-[#e8e4dd]"}`}>
                        {cmd.name}
                      </span>
                      <span className={`text-[10px] mt-0.5 ${slashMenuIndex === idx ? "text-[#e8e4dd]" : "text-[#7a776f]"}`}>
                        {cmd.description}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <div className="bg-[#3a3a36] border border-[#4a4a44] rounded-2xl overflow-hidden">
                {attachment && (
                  <div className="px-4 pt-3 flex items-center gap-2">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-[#454540] rounded-lg text-xs text-[#e8e4dd]">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
                      <span className="truncate max-w-[200px]">{attachment.name}</span>
                      <span className="text-[#7a776f]">{attachment.wordCount} words</span>
                      <button onClick={() => setAttachment(null)} className="text-[#7a776f] hover:text-[#e8e4dd] transition-colors">
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                      </button>
                    </div>
                  </div>
                )}
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => handleInputChange(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={attachment ? "Ask about this document..." : "Message Kizuna..."}
                  rows={1}
                  className="w-full resize-none px-4 pt-3 pb-1 bg-transparent text-[#e8e4dd] placeholder-[#7a776f] focus:outline-none text-sm max-h-32"
                  style={{ minHeight: "40px" }}
                />
                <div className="flex items-center justify-between px-3 pb-2.5">
                  <label className="cursor-pointer text-[#7a776f] hover:text-[#a8a49d] transition-colors p-1.5 rounded-lg hover:bg-[#454540]">
                    <input type="file" accept=".pdf,.docx,.csv,.xlsx,.txt,.md" className="hidden" onChange={handleFileUpload} />
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#7a776f]">{theme.label}</span>
                    <button onClick={isStreaming ? handleStop : handleSend} disabled={!isStreaming && !(input || "").trim()} className="p-1.5 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#454540]" title={isStreaming ? "Stop generating" : "Send"} aria-label={isStreaming ? "Stop generating" : "Send message"}>
                      {isStreaming ? (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" className="text-[#e8e4dd]"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>
                      ) : (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#a8a49d]"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                      )}
                    </button>
                  </div>
                </div>
              </div>
              {uploadError && (
                <div className="mt-2 text-[#f87171] text-xs bg-[#f8717115] px-3 py-2 rounded-lg flex items-center justify-between">
                  <span>{uploadError}</span>
                  <button onClick={() => setUploadError(null)} className="text-[#f87171] hover:text-[#e8e4dd] ml-2" aria-label="Dismiss error">&times;</button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Connectors Modal */}
      {showConnectorsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center modal-overlay" role="dialog" aria-modal="true" aria-labelledby="connectors-title" onClick={() => setShowConnectorsModal(false)}>
          <div className="bg-[#353531] border border-[#4a4a44] rounded-2xl w-full max-w-[680px] max-h-[80vh] flex flex-col shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="p-6 pb-4">
              <div className="flex items-center justify-between mb-1">
                <h2 id="connectors-title" className="text-xl font-medium text-[#e8e4dd]">Connectors</h2>
                <button onClick={() => setShowConnectorsModal(false)} className="w-8 h-8 rounded-full bg-[#454540] flex items-center justify-center text-[#a8a49d] hover:text-[#e8e4dd] transition-colors">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
              <p className="text-sm text-[#a8a49d] mb-4">
                Connect your tools to Kizuna. Authentication is powered by Composio.
              </p>
            </div>
            <div className="flex-1 overflow-y-auto px-6 pb-6">
              <div className="grid grid-cols-2 gap-3">
                {connectors.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => handleToggleConnector(c)}
                    disabled={connectingToolkit !== null && connectingToolkit !== c.id}
                    className={`flex items-center gap-3 p-3 rounded-xl transition-colors text-left w-full ${
                      c.connected
                        ? "bg-[#3a3a36] border-2 border-[#4ade80]/40 hover:border-[#4ade80]/70"
                        : connectingToolkit === c.id
                          ? "bg-[#3a3a36] border-2 border-[#d4a574]/40 animate-pulse"
                          : "bg-[#3a3a36] border border-[#4a4a44] hover:border-[#5a5a54] hover:bg-[#454540]"
                    } disabled:opacity-40 disabled:cursor-not-allowed`}
                    aria-label={c.connected ? `Disconnect ${c.name}` : `Connect ${c.name}`}
                  >
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold flex-shrink-0 ${
                      c.connected ? "bg-[#4ade80]/20 text-[#4ade80]" : "bg-[#454540] text-[#e8e4dd]"
                    }`}>
                      {c.name.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#e8e4dd] truncate">{c.name}</span>
                        {c.connected && <span className="w-1.5 h-1.5 rounded-full bg-[#4ade80] flex-shrink-0" />}
                      </div>
                      <p className="text-xs text-[#7a776f] truncate mt-0.5">
                        {connectingToolkit === c.id
                          ? "Connecting... complete auth in the new tab"
                          : c.connected
                            ? "Connected"
                            : c.description}
                      </p>
                    </div>
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      connectingToolkit === c.id
                        ? "text-[#d4a574]"
                        : c.connected
                          ? "text-[#4ade80]"
                          : "text-[#a8a49d]"
                    }`}>
                      {connectingToolkit === c.id ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                      ) : c.connected ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      )}
                    </div>
                  </button>
                ))}
              </div>
              {connectors.length === 0 && (
                <p className="text-sm text-[#7a776f] text-center py-8">No connectors available</p>
              )}
            </div>
          </div>
        </div>
      )}

      {showSettingsModal && (
        <TwoFactorSettings onClose={() => setShowSettingsModal(false)} />
      )}
    </div>
  );
}
