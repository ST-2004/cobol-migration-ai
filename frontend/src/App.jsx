import { useState } from "react";
import FileUpload from "./components/FileUpload";
import GraphSummary from "./components/GraphSummary";
import MigrationPanel from "./components/MigrationPanel";
import "./App.css";

export default function App() {
  const [jobId, setJobId] = useState(null);
  const [createdAt, setCreatedAt] = useState("");
  const [graph, setGraph] = useState(null);
  const [showMigration, setShowMigration] = useState(false);
  const [pythonCode, setPythonCode] = useState(null);

  const handleParsed = (id, ts, g) => {
    setJobId(id);
    setCreatedAt(ts);
    setGraph(g);
    setShowMigration(false);
    setPythonCode(null);
  };

  const handleReset = () => {
    setJobId(null);
    setCreatedAt("");
    setGraph(null);
    setShowMigration(false);
    setPythonCode(null);
  };

  const handleMigrationComplete = (code) => {
    setPythonCode(code);
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

            {!showMigration && !pythonCode && (
              <div className="app-actions">
                <button
                  className="btn btn--primary"
                  onClick={() => setShowMigration(true)}
                >
                  Migrate to Python
                </button>
                <button className="btn btn--secondary" onClick={handleReset}>
                  Upload Another File
                </button>
              </div>
            )}

            {showMigration && (
              <MigrationPanel
                jobId={jobId}
                createdAt={createdAt}
                onMigrationComplete={handleMigrationComplete}
              />
            )}

            {pythonCode && (
              <div className="app-actions">
                <button className="btn btn--secondary" onClick={handleReset}>
                  Start New Migration
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
