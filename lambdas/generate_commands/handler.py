"""
Phase 4: Generate Commands Lambda
Analyses generated Python output, produces pip install + run commands,
creates pre-signed S3 download URL.
"""
import ast
import json
import os
import re
import boto3
from botocore.exceptions import ClientError

JOBS_TABLE = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
FILES_BUCKET = os.environ.get("FILES_BUCKET", "cobol-mig-dev-files")

STDLIB_MODULES = {
    "os", "sys", "re", "json", "datetime", "time", "math", "random",
    "collections", "itertools", "functools", "pathlib", "typing",
    "dataclasses", "enum", "abc", "io", "struct", "decimal", "fractions",
    "statistics", "string", "textwrap", "unicodedata", "codecs",
    "logging", "warnings", "traceback", "inspect", "copy", "pprint",
    "unittest", "doctest", "argparse", "configparser", "csv",
    "hashlib", "hmac", "secrets", "uuid", "base64", "binascii",
    "pickle", "shelve", "sqlite3", "xml", "html", "http", "urllib",
    "socket", "ssl", "email", "smtplib", "ftplib", "ast", "dis",
    "gc", "weakref", "contextlib", "threading", "multiprocessing",
    "subprocess", "signal", "queue", "concurrent",
}


def detect_third_party_imports(source: str) -> list:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        imports = re.findall(r"^import\s+(\w+)|^from\s+(\w+)", source, re.MULTILINE)
        packages = [i[0] or i[1] for i in imports]
        return [p for p in packages if p and p not in STDLIB_MODULES]

    packages = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in STDLIB_MODULES:
                    packages.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top not in STDLIB_MODULES:
                    packages.add(top)
    return sorted(packages)


def handler(event, context):
    job_id = event.get("job_id")
    created_at = event.get("created_at", "")

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(JOBS_TABLE)
    item = table.get_item(Key={"job_id": job_id, "created_at": created_at})
    job = item.get("Item", {})

    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=FILES_BUCKET, Key=f"{job_id}/output.py")
    python_source = obj["Body"].read().decode("utf-8")

    packages = detect_third_party_imports(python_source)

    commands = []
    if packages:
        commands.append(f"pip install {' '.join(packages)}")
    commands.append(f"python output.py")

    download_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": FILES_BUCKET, "Key": f"{job_id}/output.py"},
        ExpiresIn=3600,
    )

    table.update_item(
        Key={"job_id": job_id, "created_at": created_at},
        UpdateExpression="SET #s = :s, commands = :c, download_url = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "complete",
            ":c": commands,
            ":u": download_url,
        },
    )

    return {**event, "commands": commands, "download_url": download_url}
