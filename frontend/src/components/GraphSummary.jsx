import "./GraphSummary.css";

export default function GraphSummary({ jobId, graph }) {
  const { paragraphs = [], variables = [], calls = [] } = graph;

  return (
    <div className="graph-summary">
      <h2 className="graph-summary__title">Parse Result</h2>
      <p className="graph-summary__job-id">Job ID: <code>{jobId}</code></p>

      <div className="graph-summary__columns">
        <section className="graph-summary__section">
          <h3>Paragraphs ({paragraphs.length})</h3>
          {paragraphs.length === 0 ? (
            <p className="graph-summary__empty">None detected</p>
          ) : (
            <table className="graph-table">
              <thead>
                <tr><th>#</th><th>Name</th></tr>
              </thead>
              <tbody>
                {paragraphs.map((p, i) => (
                  <tr key={p}><td>{i + 1}</td><td>{p}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="graph-summary__section">
          <h3>Variables ({variables.length})</h3>
          {variables.length === 0 ? (
            <p className="graph-summary__empty">None detected</p>
          ) : (
            <table className="graph-table">
              <thead>
                <tr><th>Level</th><th>Name</th><th>PIC</th></tr>
              </thead>
              <tbody>
                {variables.map((v, i) => (
                  <tr key={i}><td>{v.level}</td><td>{v.name}</td><td>{v.pic}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <section className="graph-summary__section graph-summary__calls">
        <h3>PERFORM Calls ({calls.length})</h3>
        {calls.length === 0 ? (
          <p className="graph-summary__empty">No PERFORM calls detected</p>
        ) : (
          <ul className="calls-list">
            {calls.map((c, i) => (
              <li key={i}>
                {c.from ? <><code>{c.from}</code> &rarr; <code>{c.to}</code></> : <code>{c.to}</code>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
