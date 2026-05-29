"""
Phase 0 Test — Project Scaffold & Terraform Foundation

ROLLBACK COMMANDS (if phase fails mid-way):
    # Nothing was deployed to AWS — no state to roll back.
    # To start completely fresh:
    #   rm -rf terraform/.terraform terraform/*.tfplan
    #   Remove any manually created S3/DynamoDB backend resources:
    #     aws s3 rb s3://cobol-mig-tfstate-<account_id> --force
    #     aws dynamodb delete-table --table-name cobol-mig-tflock

Run modes:
    python tests/phase_0_test.py          # unit checks only (no AWS needed)
    LIVE_TEST=1 python tests/phase_0_test.py  # validates real terraform outputs
    E2E_TEST=1 python tests/phase_0_test.py   # Playwright frontend smoke test
"""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
LIVE = os.environ.get("LIVE_TEST") == "1"
E2E = os.environ.get("E2E_TEST") == "1"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

failures = []


def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {label}")
    else:
        msg = f"{label}" + (f": {detail}" if detail else "")
        print(f"  {FAIL}  {msg}")
        failures.append(msg)


# ── 1. Directory & file structure ─────────────────────────────────────────
print("\n[1] Directory & file structure")

EXPECTED_DIRS = [
    "terraform",
    "terraform/modules/iam",
    "terraform/modules/s3",
    "terraform/modules/dynamodb",
    "terraform/modules/kms",
    "lambdas/parse_cobol",
    "lambdas/migrate",
    "lambdas/verify",
    "lambdas/compare_graphs",
    "lambdas/generate_commands",
    "frontend/src",
    "frontend/src/components",
    "tests",
    "scripts",
]

for d in EXPECTED_DIRS:
    check(f"dir exists: {d}", (ROOT / d).is_dir())

EXPECTED_FILES = [
    "terraform/main.tf",
    "terraform/variables.tf",
    "terraform/outputs.tf",
    "terraform/backend.hcl",
    "terraform/modules/iam/main.tf",
    "terraform/modules/iam/variables.tf",
    "terraform/modules/iam/outputs.tf",
    "terraform/modules/s3/main.tf",
    "terraform/modules/s3/variables.tf",
    "terraform/modules/s3/outputs.tf",
    "terraform/modules/dynamodb/main.tf",
    "terraform/modules/dynamodb/variables.tf",
    "terraform/modules/dynamodb/outputs.tf",
    "terraform/modules/kms/main.tf",
    "terraform/modules/kms/variables.tf",
    "terraform/modules/kms/outputs.tf",
    "lambdas/parse_cobol/handler.py",
    "lambdas/parse_cobol/requirements.txt",
    "lambdas/migrate/handler.py",
    "lambdas/migrate/requirements.txt",
    "lambdas/verify/handler.py",
    "lambdas/verify/requirements.txt",
    "lambdas/compare_graphs/handler.py",
    "lambdas/compare_graphs/requirements.txt",
    "lambdas/generate_commands/handler.py",
    "lambdas/generate_commands/requirements.txt",
    "frontend/src/App.jsx",
    "frontend/src/App.css",
    "frontend/package.json",
    "scripts/write_env.py",
    "tests/sample.cbl",
    ".gitignore",
]

for f in EXPECTED_FILES:
    check(f"file exists: {f}", (ROOT / f).is_file())

# ── 2. package.json sanity ──────────────────────────────────────────────
print("\n[2] frontend/package.json")

pkg_path = ROOT / "frontend" / "package.json"
if pkg_path.is_file():
    pkg = json.loads(pkg_path.read_text())
    check("package.json has 'name'", "name" in pkg)
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    check("vite is a dependency", any("vite" in k.lower() for k in deps))
    check("react is a dependency", "react" in deps)
else:
    check("package.json readable", False, "file missing")

# ── 3. Lambda handler.py syntax check ──────────────────────────────────
print("\n[3] Lambda handler.py syntax")

for fn in ["parse_cobol", "migrate", "verify", "compare_graphs", "generate_commands"]:
    path = ROOT / "lambdas" / fn / "handler.py"
    if path.is_file():
        source = path.read_text()
        try:
            ast.parse(source)
            check(f"{fn}/handler.py is valid Python", True)
        except SyntaxError as e:
            check(f"{fn}/handler.py is valid Python", False, str(e))
    else:
        check(f"{fn}/handler.py exists", False, "file missing")

# ── 4. sample.cbl quality checks ───────────────────────────────────────
print("\n[4] tests/sample.cbl quality")

cbl_path = ROOT / "tests" / "sample.cbl"
if cbl_path.is_file():
    cbl = cbl_path.read_text()
    lines = cbl.splitlines()
    check("sample.cbl >= 200 lines", len(lines) >= 200, f"got {len(lines)}")

    import re
    para_re = re.compile(r"^[ ]{0,7}([A-Z0-9][A-Z0-9\-]{0,29})\.\s*$", re.MULTILINE)
    RESERVED = {
        "IDENTIFICATION", "DIVISION", "PROGRAM-ID", "DATA", "WORKING-STORAGE",
        "SECTION", "PROCEDURE", "STOP", "RUN", "DISPLAY", "COMPUTE", "MOVE",
        "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "IF", "ELSE", "END-IF",
        "EVALUATE", "WHEN", "OTHER", "END-EVALUATE", "PERFORM", "VARYING",
        "FROM", "BY", "UNTIL", "END-PERFORM", "CALL", "USING", "GOBACK",
        "EXIT", "CONTINUE", "INITIALIZE", "INSPECT", "AUTHOR", "DATE-WRITTEN",
    }
    paragraphs = [m.group(1) for m in para_re.finditer(cbl)
                  if m.group(1).upper() not in RESERVED]
    check("sample.cbl has >= 8 paragraphs", len(paragraphs) >= 8,
          f"found: {paragraphs}")
    check("sample.cbl has EVALUATE", "EVALUATE" in cbl.upper())
    check("sample.cbl has PERFORM VARYING", "PERFORM VARYING" in cbl.upper())
    check("sample.cbl has PIC 9(", "PIC 9(" in cbl.upper())
    check("sample.cbl has PIC X(", "PIC X(" in cbl.upper())
    check("sample.cbl has 88-level condition", "88 " in cbl)
    check("sample.cbl has COMP-3", "COMP-3" in cbl.upper())
    check("sample.cbl has multi-level 01/05/10 group",
          "05  " in cbl and re.search(r"^\s+10\s+[A-Z]", cbl, re.MULTILINE) is not None)
    check("sample.cbl has IF/ELSE nesting",
          cbl.upper().count("IF ") >= 4)
else:
    check("sample.cbl exists", False)

# ── 5. Terraform validate (requires terraform CLI) ──────────────────────
print("\n[5] Terraform HCL validation")

tf_dir = ROOT / "terraform"
# Use a dummy backend override so validate doesn't need real S3
result = subprocess.run(
    ["terraform", "validate"],
    cwd=tf_dir,
    capture_output=True,
    text=True,
    env={
        **os.environ,
        "TF_CLI_ARGS_init": "-backend=false",
    },
)
# terraform validate needs init first — run init -backend=false then validate
init_result = subprocess.run(
    ["terraform", "init", "-backend=false", "-no-color"],
    cwd=tf_dir,
    capture_output=True,
    text=True,
)
if init_result.returncode == 0:
    val_result = subprocess.run(
        ["terraform", "validate", "-no-color"],
        cwd=tf_dir,
        capture_output=True,
        text=True,
    )
    check(
        "terraform validate passes",
        val_result.returncode == 0,
        val_result.stderr.strip() or val_result.stdout.strip(),
    )
else:
    check(
        "terraform init -backend=false",
        False,
        init_result.stderr[:300],
    )

# ── 6. gitignore contains sensitive files ──────────────────────────────
print("\n[6] .gitignore coverage")

gi = (ROOT / ".gitignore").read_text() if (ROOT / ".gitignore").is_file() else ""
check(".gitignore ignores terraform.tfvars", "terraform.tfvars" in gi)
check(".gitignore ignores .env.local", ".env.local" in gi)
check(".gitignore ignores node_modules", "node_modules" in gi)

# ── 7. LIVE_TEST: Terraform outputs present ─────────────────────────────
if LIVE:
    print("\n[7] LIVE: Terraform outputs")
    out = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=ROOT / "terraform",
        capture_output=True,
        text=True,
    )
    if out.returncode == 0:
        outputs = json.loads(out.stdout)
        check("files_bucket_name output exists", "files_bucket_name" in outputs)
        check("jobs_table_name output exists", "jobs_table_name" in outputs)
        check("kms_key_arn output exists", "kms_key_arn" in outputs)
    else:
        check("terraform output readable", False, out.stderr[:200])

# ── 8. E2E_TEST: Frontend loads ─────────────────────────────────────────
if E2E:
    print("\n[8] E2E: Frontend loads in browser")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("http://localhost:5173", timeout=10000)
            content = page.content()
            check("page contains 'COBOL Migration AI'",
                  "COBOL Migration AI" in content)
            browser.close()
    except Exception as e:
        check("E2E frontend check", False, str(e))

# ── Summary ─────────────────────────────────────────────────────────────
print()
if failures:
    print(f"FAILED — {len(failures)} assertion(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED — Phase 0 complete.")
