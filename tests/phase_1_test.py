"""
Phase 1 test — COBOL Parser Lambda: upload & parse.

ROLLBACK COMMANDS (if phase fails mid-apply):
  cd terraform
  terraform state rm module.lambda_parse_cobol.aws_lambda_function.this
  terraform state rm 'module.lambda_parse_cobol.aws_iam_role_policy.extra[0]'
  terraform state rm module.api_gateway.aws_apigatewayv2_api.this
  terraform state rm module.api_gateway.aws_apigatewayv2_stage.default
  terraform state rm module.api_gateway.aws_apigatewayv2_integration.parse_cobol
  terraform state rm module.api_gateway.aws_apigatewayv2_route.parse
  terraform state rm module.api_gateway.aws_lambda_permission.parse_cobol

Run modes:
  python tests/phase_1_test.py            # unit tests only (no AWS creds needed)
  LIVE_TEST=1 python tests/phase_1_test.py # integration — requires VITE_API_URL in env or .env.local
  E2E_TEST=1  python tests/phase_1_test.py # Playwright E2E — requires running dev server
"""

import json
import os
import sys
import uuid
import base64
import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
HANDLER_PATH = REPO_ROOT / "lambdas" / "parse_cobol" / "handler.py"
SAMPLE_CBL = REPO_ROOT / "tests" / "sample.cbl"
FRONTEND_ENV = REPO_ROOT / "frontend" / ".env.local"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_handler():
    """Import parse_cobol/handler.py without installing it as a package."""
    spec = importlib.util.spec_from_file_location("parse_cobol_handler", HANDLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_multipart(file_bytes: bytes, filename: str = "sample.cbl") -> tuple[bytes, str]:
    """Build a minimal multipart/form-data body."""
    boundary = "----TestBoundary1234"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def build_event(file_bytes: bytes, filename: str = "sample.cbl") -> dict:
    body, content_type = build_multipart(file_bytes, filename)
    return {
        "httpMethod": "POST",
        "isBase64Encoded": False,
        "headers": {"content-type": content_type},
        "body": body,
        "requestContext": {"http": {"method": "POST"}},
    }


# ---------------------------------------------------------------------------
# Unit tests (always run — zero AWS creds required via moto)
# ---------------------------------------------------------------------------

def test_unit():
    print("=== Unit Tests ===")
    try:
        import boto3
        from moto import mock_aws
    except ImportError:
        print("  SKIP: moto not installed. Install with: pip install moto[s3,dynamodb]")
        return True

    handler_mod = load_handler()

    BUCKET = "cobol-mig-dev-files"
    TABLE = "cobol-mig-dev-jobs"

    @mock_aws
    def run():
        import boto3
        # Create mock AWS resources
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)

        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "job_id", "KeyType": "HASH"},
                {"AttributeName": "created_at", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Patch env vars
        os.environ["FILES_BUCKET"] = BUCKET
        os.environ["JOBS_TABLE"] = TABLE

        sample_cobol = SAMPLE_CBL.read_bytes()
        event = build_event(sample_cobol)
        result = handler_mod.handler(event, {})

        # Test 1: HTTP 200
        assert result["statusCode"] == 200, f"Expected 200, got {result['statusCode']}: {result['body']}"
        print("  [PASS] HTTP 200")

        body = json.loads(result["body"])

        # Test 2: job_id is a valid UUID
        job_id = body.get("job_id", "")
        try:
            uuid.UUID(job_id)
        except ValueError:
            raise AssertionError(f"job_id is not a valid UUID: {job_id!r}")
        print(f"  [PASS] job_id is valid UUID: {job_id}")

        # Test 3: graph has paragraphs and variables
        graph = body.get("graph", {})
        assert len(graph.get("paragraphs", [])) >= 1, "Expected >= 1 paragraph"
        assert len(graph.get("variables", [])) >= 1, "Expected >= 1 variable"
        print(f"  [PASS] graph.paragraphs: {len(graph['paragraphs'])} entries")
        print(f"  [PASS] graph.variables: {len(graph['variables'])} entries")
        print(f"  [INFO] graph.calls: {len(graph.get('calls', []))} entries")

        # Test 4: S3 object was stored
        s3_obj = s3.get_object(Bucket=BUCKET, Key=f"{job_id}/source.cbl")
        assert s3_obj["ResponseMetadata"]["HTTPStatusCode"] == 200
        print(f"  [PASS] S3 object {job_id}/source.cbl exists")

        # Test 5: DynamoDB item was stored with status=parsed
        table = ddb.Table(TABLE)
        items = table.scan()["Items"]
        matching = [i for i in items if i["job_id"] == job_id]
        assert len(matching) == 1, f"Expected 1 DynamoDB item, found {len(matching)}"
        assert matching[0]["status"] == "parsed", f"Expected status=parsed, got {matching[0]['status']}"
        print(f"  [PASS] DynamoDB item status=parsed")

        # Test 6: CORS headers present
        assert "Access-Control-Allow-Origin" in result["headers"], "Missing CORS header"
        print("  [PASS] CORS headers present")

        # Test 7: parse_cobol function directly (unit without HTTP wrapper)
        cobol_str = sample_cobol.decode("utf-8", errors="replace")
        graph2 = handler_mod.parse_cobol(cobol_str)
        assert len(graph2["paragraphs"]) >= 1
        assert len(graph2["variables"]) >= 1
        print("  [PASS] parse_cobol() function works directly")

        return True

    return run()


# ---------------------------------------------------------------------------
# Integration tests (LIVE_TEST=1)
# ---------------------------------------------------------------------------

def test_integration():
    print("=== Integration Tests (LIVE_TEST=1) ===")

    # Resolve API URL from env or .env.local
    api_url = os.environ.get("VITE_API_URL", "")
    if not api_url and FRONTEND_ENV.exists():
        for line in FRONTEND_ENV.read_text().splitlines():
            if line.startswith("VITE_API_URL="):
                api_url = line.split("=", 1)[1].strip()
                break

    if not api_url:
        print("  SKIP: VITE_API_URL not set. Run terraform apply first.")
        return True

    try:
        import urllib.request
        import urllib.error
    except ImportError:
        print("  SKIP: urllib not available")
        return True

    sample_bytes = SAMPLE_CBL.read_bytes()
    body, content_type = build_multipart(sample_bytes, "sample.cbl")

    req = urllib.request.Request(
        f"{api_url}/parse",
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
            data = json.loads(resp.read())
            assert "job_id" in data, "Missing job_id in response"
            assert "graph" in data, "Missing graph in response"
            assert len(data["graph"].get("paragraphs", [])) >= 1
            print(f"  [PASS] POST /parse returned 200, job_id={data['job_id']}")
            print(f"  [PASS] graph.paragraphs: {len(data['graph']['paragraphs'])}")
    except urllib.error.HTTPError as e:
        print(f"  [FAIL] HTTP {e.code}: {e.read().decode()}")
        return False

    return True


# ---------------------------------------------------------------------------
# E2E tests (E2E_TEST=1)
# ---------------------------------------------------------------------------

def test_e2e():
    print("=== E2E Tests (E2E_TEST=1) ===")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  SKIP: playwright not installed. Install with: pip install playwright && playwright install")
        return True

    dev_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(dev_url, timeout=10000)

        # Assert drop zone is visible
        page.wait_for_selector(".drop-zone", timeout=5000)
        print("  [PASS] FileUpload drop zone rendered")

        # Upload sample.cbl via file input
        with page.expect_file_chooser() as fc_info:
            page.click(".drop-zone")
        fc = fc_info.value
        fc.set_files(str(SAMPLE_CBL))

        # Wait for GraphSummary to appear
        page.wait_for_selector(".graph-summary", timeout=15000)
        print("  [PASS] GraphSummary rendered after upload")

        # Assert paragraph table has rows
        rows = page.query_selector_all(".graph-table tbody tr")
        assert len(rows) >= 1, f"Expected >= 1 paragraph row, got {len(rows)}"
        print(f"  [PASS] Paragraph table has {len(rows)} row(s)")

        browser.close()

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failures = []

    # Unit tests always run
    try:
        ok = test_unit()
        if not ok:
            failures.append("unit")
    except Exception as e:
        print(f"  [FAIL] Unit test error: {e}")
        import traceback; traceback.print_exc()
        failures.append("unit")

    if os.environ.get("LIVE_TEST") == "1":
        try:
            ok = test_integration()
            if not ok:
                failures.append("integration")
        except Exception as e:
            print(f"  [FAIL] Integration test error: {e}")
            import traceback; traceback.print_exc()
            failures.append("integration")

    if os.environ.get("E2E_TEST") == "1":
        try:
            ok = test_e2e()
            if not ok:
                failures.append("e2e")
        except Exception as e:
            print(f"  [FAIL] E2E test error: {e}")
            import traceback; traceback.print_exc()
            failures.append("e2e")

    if failures:
        print(f"\n[FAILED] {', '.join(failures)}")
        sys.exit(1)
    else:
        print("\n[ALL PASS]")
        sys.exit(0)
