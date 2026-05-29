import { useState, useRef } from "react";
import "./FileUpload.css";

const API_URL = import.meta.env.VITE_API_URL || "";

export default function FileUpload({ onParsed }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const upload = async (file) => {
    if (!file) return;
    if (!/\.(cob|cbl)$/i.test(file.name)) {
      setError("Only .cob and .cbl files are accepted.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const res = await fetch(`${API_URL}/parse`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      onParsed(data.job_id, data.graph);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    upload(e.dataTransfer.files[0]);
  };

  const onFileChange = (e) => upload(e.target.files[0]);

  return (
    <div className="upload-wrapper">
      <div
        className={`drop-zone ${dragging ? "drop-zone--active" : ""} ${loading ? "drop-zone--loading" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !loading && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        aria-label="Upload COBOL file"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".cob,.cbl"
          className="drop-zone__input"
          onChange={onFileChange}
        />
        {loading ? (
          <div className="drop-zone__loading">
            <span className="spinner" aria-hidden="true" />
            <span>Parsing COBOL&hellip;</span>
          </div>
        ) : (
          <div className="drop-zone__prompt">
            <span className="drop-zone__icon" aria-hidden="true">&#8613;</span>
            <p>Drag &amp; drop a <code>.cob</code> or <code>.cbl</code> file here</p>
            <p className="drop-zone__sub">or click to browse</p>
          </div>
        )}
      </div>
      {error && <p className="upload-error" role="alert">{error}</p>}
    </div>
  );
}
