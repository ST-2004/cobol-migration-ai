"""
Phase 2 test — Migration Pipeline: WebSocket + Step Functions + Bedrock.

ROLLBACK COMMANDS (if phase fails mid-apply):
  cd terraform
  terraform state rm module.lambda_migrate.aws_lambda_function.this
  terraform state rm 'module.lambda_migrate.aws_iam_role_policy.extra[0]'
  terraform state rm module.lambda_ws_connect.aws_lambda_function.this
  terraform state rm 'module.lambda_ws_connect.aws_iam_role_policy.extra[0]'
  terraform state rm module.lambda_ws_disconnect.aws_lambda_function.this
  terraform state rm 'module.lambda_ws_disconnect.aws_iam_role_policy.extra[0]'
  terraform state rm module.lambda_trigger_migrate.aws_lambda_function.this
  terraform state rm 'module.lambda_trigger_migrate.aws_iam_role_policy.extra[0]'
  terraform state rm module.websocket.aws_apigatewayv2_api.ws
  terraform state rm module.websocket.aws_apigatewayv2_stage.ws_default
  terraform state rm module.websocket.aws_apigatewayv2_integration.ws_connect
  terraform state rm module.websocket.aws_apigatewayv2_integration.ws_disconnect
  terraform state rm module.websocket.aws_apigatewayv2_route.ws_connect
  terraform state rm module.websocket.aws_apigatewayv2_route.ws_disconnect
  terraform state rm module.websocket.aws_apigatewayv2_route.ws_default
  terraform state rm module.websocket.aws_lambda_permission.ws_connect
  terraform state rm module.websocket.aws_lambda_permission.ws_disconnect
  terraform state rm module.step_functions.aws_sfn_state_machine.pipeline
  terraform state rm module.step_functions.aws_iam_role.sfn
  terraform state rm module.step_functions.aws_iam_role_policy.sfn_lambda_invoke
  terraform state rm module.dynamodb.aws_dynamodb_table.connections
  terraform state rm module.api_gateway.aws_apigatewayv2_integration.trigger_migrate
  terraform state rm module.api_gateway.aws_apigatewayv2_route.migrate
  terraform state rm module.api_gateway.aws_lambda_permission.trigger_migrate

Run modes:
  python tests/phase_2_test.py            # unit tests only (no AWS creds needed)
  LIVE_TEST=1 python tests/phase_2_test.py # integration — requires deployed stack
  E2E_TEST=1  python tests/phase_2_test.py # Playwright E2E — requires running dev server
"""

import importlib.util
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).parent.parent
MIGRATE_HANDLER = REPO_ROOT / "lambdas" / "migrate" / "handler.py"
WS_CONNECT_HANDLER = REPO_ROOT / "lambdas" / "ws_connect" / "handler.py"
WS_DISCONNECT_HANDLER = REPO_ROOT / "lambdas" / "ws_disconnect" / "handler.py"
TRIGGER_HANDLER = REPO_ROOT / "lambdas" / "trigger_migrate" / "handler.py"
FRONTEND_ENV = REPO_ROOT / "frontend" / ".env.local"
SAMPLE_CBL = REPO_ROOT / "tests" / "sample.cbl"

BUCKET = "cobol-mig-dev-files"
JOBS_TABLE = "cobol-mig-dev-jobs"
CONNECTIONS_TABLE = "cobol-mig-dev-connections"


# ─── Loader helpers ──────────────────────────────────────────────────────────

def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── Unit tests ──────────────────────────────────────────────────────────────

def test_unit():
    print("=== Unit Tests ===")
    try:
        import boto3
        from moto import mock_aws
    except ImportError:
        print("  SKIP: moto not installed. pip install moto[s3,dynamodb]")
        return True

    # ── 2a: ws_connect ────────────────────────────────────────────────────────
    @mock_aws
    def test_ws_connect():
        import boto3
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=CONNECTIONS_TABLE,
            KeySchema=[{"AttributeName": "connection_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "connection_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        os.environ["CONNECTIONS_TABLE"] = CONNECTIONS_TABLE

        mod = _load(WS_CONNECT_HANDLER)
        result = mod.handler(
            {
                "requestContext": {"connectionId": "test-conn-123"},
                "queryStringParameters": {"job_id": "job-abc"},
            },
            {},
        )
        assert result["statusCode"] == 200, f"ws_connect returned {result}"

        table = ddb.Table(CONNECTIONS_TABLE)
        item = table.get_item(Key={"connection_id": "test-conn-123"}).get("Item", {})
        assert item.get("job_id") == "job-abc", f"job_id not stored: {item}"
        print("  [PASS] ws_connect stores connectionId + job_id in DynamoDB")

    test_ws_connect()

    # ── 2b: ws_disconnect ─────────────────────────────────────────────────────
    @mock_aws
    def test_ws_disconnect():
        import boto3
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName=CONNECTIONS_TABLE,
            KeySchema=[{"AttributeName": "connection_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "connection_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={"connection_id": "conn-to-delete", "job_id": "job-xyz"})
        os.environ["CONNECTIONS_TABLE"] = CONNECTIONS_TABLE

        mod = _load(WS_DISCONNECT_HANDLER)
        result = mod.handler(
            {"requestContext": {"connectionId": "conn-to-delete"}},
            {},
        )
        assert result["statusCode"] == 200
        item = table.get_item(Key={"connection_id": "conn-to-delete"}).get("Item")
        assert item is None, "Item should be deleted"
        print("  [PASS] ws_disconnect removes connectionId from DynamoDB")

    test_ws_disconnect()

    # ── 2c: migrate Lambda ────────────────────────────────────────────────────
    @mock_aws
    def test_migrate():
        import boto3

        # Create S3 bucket and upload sample COBOL
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        job_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        sample_cobol = SAMPLE_CBL.read_bytes() if SAMPLE_CBL.exists() else b"IDENTIFICATION DIVISION.\nPROCEDURE DIVISION.\nMAIN-PARA.\nSTOP RUN."
        s3.put_object(Bucket=BUCKET, Key=f"{job_id}/source.cbl", Body=sample_cobol)

        # Create DynamoDB jobs table
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        jobs_table = ddb.create_table(
            TableName=JOBS_TABLE,
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
        jobs_table.put_item(Item={
            "job_id": job_id,
            "created_at": created_at,
            "status": "parsed",
        })

        os.environ["JOBS_TABLE"] = JOBS_TABLE
        os.environ["FILES_BUCKET"] = BUCKET
        os.environ["WS_ENDPOINT"] = ""
        os.environ["BEDROCK_MODEL_ID"] = "anthropic.claude-sonnet-4-5"

        # Build 5 fake streaming token chunks
        def _fake_converse_stream(**kwargs):
            tokens = ["def ", "main_para", "():\n", "    pass\n", "# done\n"]

            def _stream():
                for t in tokens:
                    yield {"contentBlockDelta": {"delta": {"text": t}}}

            return {"stream": _stream()}

        mod = _load(MIGRATE_HANDLER)

        pushed_chunks = []

        # Patch boto3 clients inside the handler
        mock_bedrock = MagicMock()
        mock_bedrock.converse_stream.side_effect = _fake_converse_stream
        mock_bedrock.exceptions.ThrottlingException = Exception

        mock_ws_client = MagicMock()
        mock_ws_client.exceptions.GoneException = Exception
        mock_ws_client.post_to_connection.side_effect = lambda **kw: pushed_chunks.append(kw["Data"])

        # Snapshot real clients before patching to avoid recursive mock
        real_s3 = boto3.client("s3", region_name="us-east-1")
        real_resource = boto3.resource("dynamodb", region_name="us-east-1")

        with patch("boto3.client") as mock_client_factory, \
             patch("boto3.resource") as mock_resource_factory:

            mock_resource_factory.return_value = real_resource

            def _client_factory(service, **kwargs):
                if service == "s3":
                    return real_s3
                if service == "bedrock-runtime":
                    return mock_bedrock
                if service == "apigatewaymanagementapi":
                    return mock_ws_client
                return MagicMock()

            mock_client_factory.side_effect = _client_factory

            result = mod.handler(
                {"job_id": job_id, "created_at": created_at, "connection_id": ""},
                {},
            )

        assert result["status"] == "migrated", f"Expected migrated, got: {result}"
        print("  [PASS] migrate handler returns status=migrated")

        # Bedrock was called
        assert mock_bedrock.converse_stream.called, "Expected bedrock.converse_stream to be called"
        print("  [PASS] bedrock.converse_stream was called")

        # output.py saved to S3
        obj = s3.get_object(Bucket=BUCKET, Key=f"{job_id}/output.py")
        python_code = obj["Body"].read().decode("utf-8")
        assert len(python_code) > 0, "output.py is empty"
        print(f"  [PASS] output.py saved to S3 ({len(python_code)} bytes)")

        # DynamoDB status updated to migrated
        item = jobs_table.get_item(Key={"job_id": job_id, "created_at": created_at}).get("Item", {})
        assert item.get("status") == "migrated", f"Expected migrated, got {item.get('status')}"
        print("  [PASS] DynamoDB status updated to 'migrated'")

    test_migrate()

    # ── 2d: token streaming (with WS connection) ──────────────────────────────
    @mock_aws
    def test_migrate_ws_streaming():
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        job_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        s3.put_object(Bucket=BUCKET, Key=f"{job_id}/source.cbl", Body=b"IDENTIFICATION DIVISION.\nPROCEDURE DIVISION.\nSTOP RUN.")

        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        jobs_table = ddb.create_table(
            TableName=JOBS_TABLE,
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
        jobs_table.put_item(Item={"job_id": job_id, "created_at": created_at, "status": "parsed"})

        os.environ["JOBS_TABLE"] = JOBS_TABLE
        os.environ["FILES_BUCKET"] = BUCKET
        os.environ["WS_ENDPOINT"] = "https://fake-ws.execute-api.us-east-1.amazonaws.com/dev"

        tokens_sent = []

        def _fake_stream(**kwargs):
            for t in ["chunk1", "chunk2", "chunk3", "chunk4", "chunk5"]:
                yield {"contentBlockDelta": {"delta": {"text": t}}}

        mock_bedrock = MagicMock()
        mock_bedrock.converse_stream.side_effect = lambda **kw: {"stream": _fake_stream()}
        mock_bedrock.exceptions.ThrottlingException = Exception

        mock_ws = MagicMock()
        mock_ws.exceptions.GoneException = Exception

        def _ws_push(**kw):
            tokens_sent.append(json.loads(kw["Data"].decode("utf-8")))

        mock_ws.post_to_connection.side_effect = _ws_push

        mod = _load(MIGRATE_HANDLER)

        real_s3_ws = boto3.client("s3", region_name="us-east-1")
        real_resource_ws = boto3.resource("dynamodb", region_name="us-east-1")

        with patch("boto3.client") as mock_client_factory, \
             patch("boto3.resource") as mock_resource_factory:

            mock_resource_factory.return_value = real_resource_ws

            def _client_factory(service, **kwargs):
                if service == "s3":
                    return real_s3_ws
                if service == "bedrock-runtime":
                    return mock_bedrock
                if service == "apigatewaymanagementapi":
                    return mock_ws
                return MagicMock()

            mock_client_factory.side_effect = _client_factory

            result = mod.handler(
                {"job_id": job_id, "created_at": created_at, "connection_id": "conn-99"},
                {},
            )

        token_pushes = [m for m in tokens_sent if "token" in m]
        done_pushes  = [m for m in tokens_sent if "done" in m]

        assert len(token_pushes) >= 5, f"Expected at least 5 token pushes, got {len(token_pushes)}"
        print(f"  [PASS] {len(token_pushes)} token chunks pushed to WebSocket")

        assert len(done_pushes) == 1, "Expected exactly 1 done signal"
        print("  [PASS] WebSocket done signal sent")

    test_migrate_ws_streaming()
    return True


# ─── Integration tests (LIVE_TEST=1) ─────────────────────────────────────────

def test_integration():
    print("=== Integration Tests (LIVE_TEST=1) ===")

    api_url = os.environ.get("VITE_API_URL", "")
    if not api_url and FRONTEND_ENV.exists():
        for line in FRONTEND_ENV.read_text().splitlines():
            if line.startswith("VITE_API_URL="):
                api_url = line.split("=", 1)[1].strip()

    if not api_url:
        print("  SKIP: VITE_API_URL not set.")
        return True

    import urllib.request
    import urllib.error

    # Step 1: Upload and parse COBOL
    sample_bytes = SAMPLE_CBL.read_bytes()
    boundary = "----TestBoundary9876"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="sample.cbl"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + sample_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{api_url}/parse",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            parse_data = json.loads(resp.read())
            job_id = parse_data["job_id"]
            created_at = parse_data.get("created_at", "")
            print(f"  [PASS] /parse returned job_id={job_id}")
    except urllib.error.HTTPError as e:
        print(f"  [FAIL] /parse HTTP {e.code}: {e.read().decode()}")
        return False

    # Step 2: Trigger migration
    migrate_req = urllib.request.Request(
        f"{api_url}/migrate",
        data=json.dumps({"job_id": job_id, "created_at": created_at}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(migrate_req, timeout=30) as resp:
            migrate_data = json.loads(resp.read())
            execution_arn = migrate_data.get("execution_arn", "")
            print(f"  [PASS] /migrate returned execution_arn={execution_arn[:40]}…")
    except urllib.error.HTTPError as e:
        print(f"  [FAIL] /migrate HTTP {e.code}: {e.read().decode()}")
        return False

    # Step 3: Poll DynamoDB for status=migrated (120s timeout)
    import boto3
    ddb = boto3.resource("dynamodb")
    jobs_table_name = ""
    if FRONTEND_ENV.exists():
        for line in FRONTEND_ENV.read_text().splitlines():
            if line.startswith("JOBS_TABLE="):
                jobs_table_name = line.split("=", 1)[1].strip()

    if not jobs_table_name:
        print("  INFO: JOBS_TABLE not in .env.local — skipping DynamoDB poll")
        return True

    table = ddb.Table(jobs_table_name)
    deadline = time.time() + 120
    while time.time() < deadline:
        resp = table.query(
            KeyConditionExpression="job_id = :j",
            ExpressionAttributeValues={":j": job_id},
            Limit=1,
        )
        items = resp.get("Items", [])
        if items and items[0].get("status") == "migrated":
            print(f"  [PASS] DynamoDB status=migrated for job {job_id}")
            return True
        print(f"  [INFO] status={items[0].get('status') if items else 'unknown'}, waiting…")
        time.sleep(2)

    print(f"  [FAIL] Timed out waiting for status=migrated")
    return False


# ─── E2E tests (E2E_TEST=1) ──────────────────────────────────────────────────

def test_e2e():
    print("=== E2E Tests (E2E_TEST=1) ===")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  SKIP: playwright not installed. pip install playwright && playwright install")
        return True

    dev_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(dev_url, timeout=10000)

        # Phase 1 flow: upload
        page.wait_for_selector(".drop-zone", timeout=5000)
        with page.expect_file_chooser() as fc_info:
            page.click(".drop-zone")
        fc_info.value.set_files(str(SAMPLE_CBL))

        page.wait_for_selector(".graph-summary", timeout=15000)
        print("  [PASS] GraphSummary rendered after upload")

        # Click Migrate to Python
        page.click("button:has-text('Migrate to Python')")
        print("  [PASS] Clicked 'Migrate to Python'")

        # Wait for migration panel to appear
        page.wait_for_selector(".migration-panel", timeout=5000)
        print("  [PASS] MigrationPanel rendered")

        # Migration starts: wait for terminal to appear with tokens (120s for Bedrock)
        page.wait_for_selector(".migration-panel__terminal", timeout=10000)

        # Wait until the terminal has some content (up to 120s for real Bedrock call)
        deadline = time.time() + 120
        while time.time() < deadline:
            content = page.text_content(".migration-panel__terminal") or ""
            if len(content.strip()) > 20:
                break
            time.sleep(1)

        terminal_text = page.text_content(".migration-panel__terminal") or ""
        assert len(terminal_text.strip()) > 0, "Terminal is empty — no tokens received"
        print(f"  [PASS] Terminal received {len(terminal_text)} chars of Python output")

        browser.close()

    return True


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = []

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
