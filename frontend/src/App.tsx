import { useEffect, useRef, useState } from "react";

const API_URL = "http://localhost:8000";

interface Source {
  source_url: string;
  source_file: string;
  snippet: string;
}

interface Message {
  role: "user" | "bot";
  content: string;
  sources?: Source[];
}

const SUGGESTIONS = [
  "Is CCSU a commuter school or do students live on campus?",
  "Which professors are highly rated?",
  "How do students describe safety at CCSU?",
  "What do students say about the food and dorms?",
];

function sourceLabel(s: Source): string {
  if (s.source_url.includes("ratemyprofessors")) return "RateMyProfessors";
  if (s.source_url.includes("reddit")) return "Reddit r/ccsu";
  if (s.source_url.includes("niche")) return "Niche";
  if (s.source_url.includes("usnews")) return "US News";
  return s.source_file;
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || loading) return;

    setMessages((m) => [...m, { role: "user", content: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question }),
      });
      if (!res.ok) throw new Error(`Server error (${res.status})`);
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { role: "bot", content: data.answer, sources: data.sources },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "bot",
          content:
            "Sorry — I couldn't reach the backend. Make sure the API server " +
            "is running on port 8000.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>The Unofficial Guide — CCSU</h1>
        <p>
          Honest, unfiltered answers about Central CT State University, grounded
          in student reviews from RateMyProfessors, Reddit, and Niche.
        </p>
      </header>

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p>Ask me anything about CCSU. I only answer from real student sources.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`row ${m.role}`}>
            <div className="bubble">
              {m.content}
              {m.sources && m.sources.length > 0 && (
                <div className="sources">
                  <div className="label">Sources</div>
                  {m.sources.map((s, j) => (
                    <a
                      key={j}
                      href={s.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {sourceLabel(s)}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="row bot">
            <div className="bubble typing">Searching the reviews…</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about professors, dorms, safety, campus life…"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
