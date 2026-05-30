import { useEffect, useRef, useState } from "react";
import "./MigrationPanel.css";

const API_URL = import.meta.env.VITE_API_URL || "";
const WS_URL = import.meta.env.VITE_WS_URL || "";

export default function MigrationPanel({ jobId, createdAt, onMigrationComplete }) {
  const [status, setStatus] = useState("idle"); // idle | connecting | migrating | done | error
  const [tokens, setTokens] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const terminalRef = useRef(null);
  const wsRef = useRef(null);
  const accumulatedRef = useRef(""); // always holds latest token string (avoids stale closure)
  const completedRef = useRef(false); // prevents double-call to onMigrationComplete

  // Auto-scroll terminal to bottom as tokens arrive
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [tokens]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const startMigration = () => {
    if (!WS_URL) {
      setErrorMsg("WebSocket URL not configured. Run terraform apply first.");
      setStatus("error");
      return;
    }

    setStatus("connecting");
    setTokens("");
    setErrorMsg("");
    accumulatedRef.current = "";
    completedRef.current = false;

    // Build WebSocket URL with job_id query param
    const wsUrl = `${WS_URL}?job_id=${encodeURIComponent(jobId)}`;
    // Convert https WS URL to wss if needed (API GW websocket endpoint starts with wss://)
    const ws = new WebSocket(wsUrl.replace(/^https?:\/\//, "wss://").replace(/^wss:\/\//, "wss://"));
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("migrating");
      // Trigger the migration pipeline via HTTP API
      fetch(`${API_URL}/migrate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, created_at: createdAt }),
      }).catch((err) => {
        setErrorMsg(`Failed to start migration: ${err.message}`);
        setStatus("error");
        ws.close();
      });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.token) {
          accumulatedRef.current += data.token;
          setTokens((prev) => prev + data.token);
        }
        if (data.done) {
          completedRef.current = true;
          setStatus("done");
          ws.close();
          if (onMigrationComplete) {
            onMigrationComplete(accumulatedRef.current);
          }
        }
        if (data.error) {
          setErrorMsg(data.error);
          setStatus("error");
          ws.close();
        }
      } catch {
        // Non-JSON message — ignore
      }
    };

    ws.onerror = () => {
      setErrorMsg("WebSocket connection error. Check that the backend is deployed.");
      setStatus("error");
    };

    ws.onclose = (evt) => {
      if (completedRef.current) return; // already handled by done message
      if (accumulatedRef.current.length > 0) {
        setStatus("done");
        if (onMigrationComplete) onMigrationComplete(accumulatedRef.current);
      } else if (evt.code !== 1000) {
        setErrorMsg(`WebSocket closed unexpectedly (code ${evt.code})`);
        setStatus("error");
      }
    };
  };

  return (
    <div className="migration-panel">
      <div className="migration-panel__header">
        <h2 className="migration-panel__title">Migration Pipeline</h2>
        {status === "migrating" && (
          <div className="migration-panel__progress">
            <div className="migration-panel__bar" />
          </div>
        )}
        {status === "done" && (
          <span className="migration-panel__badge migration-panel__badge--done">
            Migration Complete
          </span>
        )}
        {status === "error" && (
          <span className="migration-panel__badge migration-panel__badge--error">
            Error
          </span>
        )}
      </div>

      {status === "idle" && (
        <div className="migration-panel__start">
          <p className="migration-panel__hint">
            The parsed COBOL graph is ready. Click below to migrate to Python using Claude AI.
          </p>
          <button className="btn btn--primary" onClick={startMigration}>
            Migrate to Python
          </button>
        </div>
      )}

      {(status === "connecting" || status === "migrating" || status === "done") && (
        <div className="migration-panel__terminal-wrap">
          <div className="migration-panel__terminal-label">
            {status === "connecting" ? "Connecting…" : status === "migrating" ? "Streaming output…" : "Output"}
          </div>
          <pre className="migration-panel__terminal" ref={terminalRef}>
            {tokens || (status === "connecting" ? "Establishing WebSocket connection…" : "")}
            {status === "migrating" && <span className="migration-panel__cursor" />}
          </pre>
        </div>
      )}

      {errorMsg && (
        <div className="migration-panel__error">{errorMsg}</div>
      )}
    </div>
  );
}
