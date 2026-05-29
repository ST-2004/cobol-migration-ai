"""
Phase 3: Compare Graphs Lambda
Diffs the COBOL paragraph graph vs Python function graph using networkx.
"""
import json
import os
import boto3

JOBS_TABLE = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")


def compare(cobol_graph: dict, python_graph: dict) -> dict:
    try:
        import networkx as nx
    except ImportError:
        return {"match_score": 0.0, "error": "networkx not available"}

    cg = nx.DiGraph()
    pg = nx.DiGraph()

    for p in cobol_graph.get("paragraphs", []):
        cg.add_node(p.lower().replace("-", "_"))
    for call in cobol_graph.get("calls", []):
        src = call.get("from", "").lower().replace("-", "_")
        dst = call.get("to", "").lower().replace("-", "_")
        if src and dst:
            cg.add_edge(src, dst)

    for f in python_graph.get("functions", []):
        pg.add_node(f.lower())

    cobol_nodes = set(cg.nodes())
    python_nodes = set(pg.nodes())

    missing = list(cobol_nodes - python_nodes)
    extra = list(python_nodes - cobol_nodes)
    matched = cobol_nodes & python_nodes

    total = len(cobol_nodes) if cobol_nodes else 1
    score = len(matched) / total

    return {
        "match_score": round(score, 4),
        "missing_in_python": missing,
        "extra_in_python": extra,
        "edge_diff": [],
    }


def handler(event, context):
    job_id = event.get("job_id")
    created_at = event.get("created_at", "")

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(JOBS_TABLE)
    item = table.get_item(Key={"job_id": job_id, "created_at": created_at})
    job = item.get("Item", {})

    cobol_graph = job.get("graph", {})
    verify_result = job.get("verify_result", {})

    result = compare(cobol_graph, verify_result)

    table.update_item(
        Key={"job_id": job_id, "created_at": created_at},
        UpdateExpression="SET #s = :s, compare_result = :r",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "compared", ":r": result},
    )

    return {**event, "compare_result": result}
