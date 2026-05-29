import { useState } from "react";
import FileUpload from "./components/FileUpload";
import GraphSummary from "./components/GraphSummary";
import "./App.css";

export default function App() {
  const [jobId, setJobId] = useState(null);
  const [graph, setGraph] = useState(null);

  const handleParsed = (id, g) => {
    setJobId(id);
    setGraph(g);
  };

  const handleReset = () => {
    setJobId(null);
    setGraph(null);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="app-logo">COBOL Migration AI</div>
      </header>
      <main className="app-main">
        {!graph ? (
          <FileUpload onParsed={handleParsed} />
        ) : (
          <>
            <GraphSummary jobId={jobId} graph={graph} />
            <div className="app-actions">
              <button className="btn btn--secondary" onClick={handleReset}>
                Upload Another File
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
