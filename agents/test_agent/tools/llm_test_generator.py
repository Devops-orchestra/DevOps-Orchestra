"""Generate language-specific tests via LLM and execute them with pytest/npm/mvn.
Supports retry feedback with prior generated code and failure logs.
"""
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from jinja2 import Template
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import TestResultsEvent
from shared_modules.kafka_event_bus.topics import TEST_RESULTS
from agents.test_agent.tools.jira_use_case_tool import get_jira_use_case

REPO_BASE_PATH = "/tmp/gitops_repos"

SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "env", "dist", "build", "target"}

# Cap retry context so prompts stay within model limits
MAX_RETRY_CODE_CHARS = 24_000
MAX_RETRY_LOG_CHARS = 16_000


class TestResult:
    def __init__(self, passed: bool, logs: str, total: int = 1, coverage: float = None):
        self.passed = passed
        self.logs = logs
        self.total = total
        self.coverage = coverage


def extract_test_results(logs: str, language: str) -> Tuple[int, int, int]:
    if language == "python":
        match = re.search(r"=+ (\d+) passed.*=", logs)
        total_match = re.search(r"=+ (\d+) (?:passed|failed|skipped|xfailed|xpassed|errors?)", logs)
        failed_match = re.search(r"=+ (\d+) failed.*=", logs)
        passed = int(match.group(1)) if match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        total = int(total_match.group(1)) if total_match else passed + failed

    elif language == "node":
        passed_match = re.search(r"(\d+)\s+passed", logs)
        failed_match = re.search(r"(\d+)\s+failed", logs)
        total_match = re.search(r"(\d+)\s+total", logs)
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        total = int(total_match.group(1)) if total_match else passed + failed

    elif language == "java":
        match = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)", logs)
        if match:
            total = int(match.group(1))
            failed = int(match.group(2)) + int(match.group(3))
            passed = total - failed
        else:
            total = 1
            passed = 0
            failed = 1

    elif language == "go":
        match = re.search(r"^(?:ok|\?)\s+.*\s+(\d+)\s+passed", logs, re.M)
        fail_match = re.search(r"FAIL\s+.*\s+(\d+)\s+failed", logs, re.M)
        passed = int(match.group(1)) if match else (0 if fail_match else 1)
        failed = int(fail_match.group(1)) if fail_match else 0
        total = passed + failed if (passed or failed) else 1

    else:
        total = 1
        passed = 1 if "pass" in logs.lower() or "ok" in logs.lower() else 0
        failed = 1 - passed

    return total, passed, failed


def _find_first_file(repo_path: str, names: list) -> Optional[Path]:
    repo = Path(repo_path)
    if not repo.is_dir():
        return None
    for root, dirs, files in os.walk(repo_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name in files:
                return Path(root) / name
    return None


def detect_language(repo_path: str) -> str:
    """Detect primary language from repo (root and subfolders). Priority: node > python > java > go > cpp."""
    if _find_first_file(repo_path, ["package.json"]):
        return "node"
    if _find_first_file(repo_path, ["requirements.txt", "pyproject.toml", "setup.py"]):
        return "python"
    if _find_first_file(repo_path, ["pom.xml", "build.gradle", "build.gradle.kts"]):
        return "java"
    if _find_first_file(repo_path, ["go.mod", "go.sum"]):
        return "go"
    if _find_first_file(repo_path, ["CMakeLists.txt"]):
        return "cpp"
    # Fallback: check repo root only
    if os.path.exists(os.path.join(repo_path, "package.json")):
        return "node"
    if os.path.exists(os.path.join(repo_path, "requirements.txt")):
        return "python"
    if os.path.exists(os.path.join(repo_path, "pom.xml")) or os.path.exists(os.path.join(repo_path, "build.gradle")):
        return "java"
    if os.path.exists(os.path.join(repo_path, "go.mod")):
        return "go"
    if os.path.exists(os.path.join(repo_path, "CMakeLists.txt")):
        return "cpp"
    return "unknown"


def read_test_prompt_template() -> Template:
    path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "shared_modules", "llm_config", "prompts", "test_prompt.txt"
    )
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())


def strip_markdown_blocks(content: str) -> str:
    content = re.sub(r"(?s)```(?:\w+)?\s*(.*?)```", r"\1", content)
    return content.strip()


def generate_tests_with_llm(
    repo_path: str,
    state: DevOpsAgentState,
    jira_ticket: Optional[str] = None,
) -> str:
    """
    Generate language-specific tests. Uses Jira use case (via jira_use_case_tool) when jira_ticket
    is provided; combines with code context and passes target language so the LLM outputs tests
    in Python, Java, JavaScript, Go, or C++ as appropriate.
    """
    logger.info("[Test Agent] Preparing LLM prompt for test generation.")

    jira_use_case_text = ""
    if jira_ticket:
        try:
            use_case = get_jira_use_case(jira_ticket)
            jira_use_case_text = (
                f"Jira ticket: {use_case.key}\n"
                f"Summary: {use_case.summary}\n"
                f"Description: {use_case.description}\n"
                f"Acceptance criteria:\n" + "\n".join(f"- {c}" for c in (use_case.acceptance_criteria or [])[:10])
            )
            logger.info(f"[Test Agent] Using Jira use case for {jira_ticket}")
        except Exception as e:
            logger.warning(f"[Test Agent] Jira use case fetch failed: {e}")
            jira_use_case_text = "(Jira ticket provided but fetch failed; generate tests from code only.)"
    else:
        jira_use_case_text = "(No Jira ticket provided; generate tests from application code only.)"

    language = detect_language(repo_path)
    logger.info(f"[Test Agent] Detected language: {language}")

    context_blocks = []
    gm = getattr(state, "git_meta", None)
    if gm and (gm.diff_summary or gm.changed_files):
        if gm.diff_summary:
            context_blocks.append(f"### Git change summary\n{gm.diff_summary[:6000]}")
        if gm.changed_files:
            cf = "\n".join(f"- {p}" for p in gm.changed_files[:120])
            context_blocks.append(f"### Changed files\n{cf}")
    idx = getattr(state, "index", None)
    if idx and idx.status == StatusEnum.SUCCESS and idx.index_root:
        context_blocks.append(
            f"### Code index\nArtifacts: `{idx.index_root}` "
            f"({idx.symbol_count} symbols, {idx.file_count} Python files, backend={idx.embedding_backend or 'n/a'})."
        )
    if state.llm_context_memory:
        context_blocks.append(f"### Indexed code context (prioritize changed symbols)\n{state.llm_context_memory}")
    if not context_blocks:
        context_blocks.append("(No additional code context in state.)")
    code_context = "\n\n".join(context_blocks)

    retry_previous_code = ""
    retry_failure_logs = ""
    if state.test_results.retries > 0:
        prev_code = (state.test_results.last_generated_code or "").strip()
        prev_logs = (state.test_results.last_run_failure_logs or "").strip()
        if prev_code or prev_logs:
            retry_previous_code = prev_code[:MAX_RETRY_CODE_CHARS]
            retry_failure_logs = prev_logs[:MAX_RETRY_LOG_CHARS]
            logger.info(
                "[Test Agent] Retry: including previous test code (%s chars) and failure logs (%s chars) for LLM.",
                len(retry_previous_code),
                len(retry_failure_logs),
            )

    prompt_template = read_test_prompt_template()
    prompt = prompt_template.render(
        context=code_context,
        jira_use_case=jira_use_case_text,
        language=language,
        retry_previous_code=retry_previous_code,
        retry_failure_logs=retry_failure_logs,
    )

    logger.info("[Test Agent] Sending prompt to LLM.")
    response = run_prompt(prompt, model="llama-3.3-70b-versatile", temperature=0.3)
    test_code = strip_markdown_blocks(response)

    logger.info("[Test Agent] LLM test code generation complete.")
    return test_code


def run_tests_for_language(repo_path: str, test_code: str, state: Optional[DevOpsAgentState] = None) -> TestResult:
    config = state.repo_context.config if state and hasattr(state, "repo_context") and hasattr(state.repo_context, "config") else {}
    test_cfg = config.get("testing", {})
    enabled = test_cfg.get("enabled", True)
    framework = test_cfg.get("framework", None)
    command = test_cfg.get("command", None)

    if not enabled:
        logger.info("[Test Agent] Testing is disabled in config. Skipping tests.")
        return TestResult(True, "Testing disabled in config.", total=0, coverage=None)

    language = detect_language(repo_path)

    if language == "python":
        test_file = os.path.join(repo_path, "autogen_tests.py")
        default_cmd = ["pytest", test_file]
    elif language == "node":
        test_file = os.path.join(repo_path, "autogen.test.js")
        default_cmd = ["npm", "test"]
    elif language == "java":
        test_file = os.path.join(repo_path, "AutogenTest.java")
        default_cmd = ["mvn", "test"]
    elif language == "go":
        test_file = os.path.join(repo_path, "autogen_test.go")
        default_cmd = ["go", "test", "-v", "./..."]
    elif language == "cpp":
        test_file = os.path.join(repo_path, "autogen_test.cpp")
        default_cmd = []  # C++ often needs custom build; we'll try ctest if CMakeLists exists
    else:
        raise ValueError(f"[Test Agent] Unsupported language for testing: {language}")

    with open(test_file, "w") as f:
        f.write(test_code)

    logger.info(f"[Test Agent] Running tests using language: {language}")
    try:
        run_cmd = None
        if command:
            run_cmd = command.split() if isinstance(command, str) else command
        elif framework:
            fw = framework.lower()
            if fw == "pytest":
                run_cmd = ["pytest", test_file]
            elif fw == "unittest":
                run_cmd = ["python", "-m", "unittest", test_file]
            elif fw == "npm" or fw == "jest" or fw == "mocha":
                run_cmd = ["npm", "test"]
            elif fw in ("maven", "mvn"):
                run_cmd = ["mvn", "test"]
            elif fw == "junit":
                run_cmd = ["java", "-cp", repo_path, "org.junit.runner.JUnitCore", "AutogenTest"]
            elif fw == "gradle":
                run_cmd = ["./gradlew", "test"] if os.name != "nt" else ["gradlew.bat", "test"]
            elif fw == "go":
                run_cmd = ["go", "test", "-v", "./..."]
            else:
                run_cmd = default_cmd
        else:
            run_cmd = default_cmd

        if language == "cpp" and not run_cmd:
            logger.info("[Test Agent] C++ test file written; run build and ctest manually or add test target to CMake.")
            return TestResult(True, "C++ test file generated. Integrate with your CMake/CTest and run locally.", total=1)

        if not run_cmd:
            return TestResult(False, "No test command configured.")

        logger.info(f"[Test Agent] Running: {' '.join(run_cmd)}")
        result = subprocess.run(
            run_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,
        )

        logs = result.stdout + result.stderr
        total, passed_count, failed_count = extract_test_results(logs, language)

        test_result = TestResult(
            passed=passed_count > 0 and failed_count == 0,
            logs=logs,
            total=total,
            coverage=None,
        )

        if test_result.passed:
            repo_name = os.path.basename(repo_path.rstrip(os.sep))
            event = TestResultsEvent(
                repo=repo_name,
                total_tests=total,
                passed=passed_count,
                failed=failed_count,
                coverage=None,
                logs=logs,
            )
            publish_event(TEST_RESULTS, event.model_dump())
            logger.info(f"[Test Agent] TEST_RESULTS event published for repo: {repo_name}")

        return test_result

    except subprocess.TimeoutExpired:
        logger.error("[Test Agent] Test run timed out.")
        return TestResult(False, "Test run timed out.")
    except Exception as e:
        logger.error(f"[Test Agent] Error while running tests: {e}")
        return TestResult(False, str(e))
