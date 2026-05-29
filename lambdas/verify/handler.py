"""
Phase 3: Verify Lambda
Runs Python AST validation on generated output.py,
checks syntax, forbidden constructs, and paragraph coverage.
"""
import ast
import json
import os
import boto3

JOBS_TABLE = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
FILES_BUCKET = os.environ.get("FILES_BUCKET", "cobol-mig-dev-files")

FORBIDDEN = {"exec", "eval", "__import__"}


def verify_python(source: str, expected_paragraphs: list) -> dict:
    issues = []
    functions = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"valid": False, "functions": [], "issues": [f"SyntaxError: {e}"]}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        if isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in FORBIDDEN:
                issues.append(f"Forbidden call: {name}()")

    para_lower = [p.lower().replace("-", "_") for p in expected_paragraphs]
    func_lower = [f.lower() for f in functions]
    for para in para_lower:
        if para not in func_lower:
            issues.append(f"Missing function for paragraph: {para}")

    return {"valid": len(issues) == 0, "functions": functions, "issues": issues}


def handler(event, context):
    job_id = event.get("job_id")
    created_at = event.get("created_at", "")

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(JOBS_TABLE)
    item = table.get_item(Key={"job_id": job_id, "created_at": created_at})
    job = item.get("Item", {})

    graph = job.get("graph", {})
    paragraphs = graph.get("paragraphs", [])

    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=FILES_BUCKET, Key=f"{job_id}/output.py")
    python_source = obj["Body"].read().decode("utf-8")

    result = verify_python(python_source, paragraphs)

    table.update_item(
        Key={"job_id": job_id, "created_at": created_at},
        UpdateExpression="SET #s = :s, verify_result = :r",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "verified", ":r": result},
    )

    return {**event, "verify_result": result}
