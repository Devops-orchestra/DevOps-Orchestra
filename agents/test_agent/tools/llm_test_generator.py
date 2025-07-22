import os
import re
import subprocess
from jinja2 import Template
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.llm_config.model_wrapper import run_prompt
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import TestResultsEvent
from shared_modules.kafka_event_bus.topics import TEST_RESULTS

REPO_BASE_PATH = "/tmp/gitops_repos"

class TestResult:
    def __init__(self, passed: bool, logs: str, total: int = 1, coverage: float = None):
        self.passed = passed
        self.logs = logs
        self.total = total
        self.coverage = coverage



def extract_test_results(logs: str, language: str) -> tuple[int, int, int]:
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
        # Example: Tests run: 10, Failures: 2, Errors: 0, Skipped: 0
        match = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)", logs)
        if match:
            total = int(match.group(1))
            failed = int(match.group(2)) + int(match.group(3))
            passed = total - failed
        else:
            total = 1
            passed = 0
            failed = 1

    else:
        total = 1
        passed = 1 if "pass" in logs.lower() else 0
        failed = 1 - passed

    return total, passed, failed



def detect_language(repo_path: str) -> str:
    if os.path.exists(os.path.join(repo_path, "package.json")):
        return "node"
    if os.path.exists(os.path.join(repo_path, "requirements.txt")):
        return "python"
    if os.path.exists(os.path.join(repo_path, "pom.xml")) or os.path.exists(os.path.join(repo_path, "build.gradle")):
        return "java"
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
    """
    Removes markdown formatting like ```python, ```text, and any 'Test Code' headers.
    """
    content = re.sub(r"(?s)```(?:\w+)?\s*(.*?)```", r"\1", content)
    return content.strip()

def generate_tests_with_llm(repo_path: str, state: DevOpsAgentState) -> str:
    """
    Renders the test prompt with context and calls the LLM to generate tests.
    """
    logger.info("[Test Agent] Preparing LLM prompt for test generation.")
    prompt_template = read_test_prompt_template()
    prompt = prompt_template.render(context=state.llm_context_memory)

    logger.info("[Test Agent] Sending prompt to LLM.")
    response = run_prompt(prompt, model="llama-3.3-70b-versatile", temperature=0.3)
    test_code = strip_markdown_blocks(response)

    logger.info("[Test Agent] LLM test code generation complete.")
    return test_code

def run_tests_for_language(repo_path: str, test_code: str, state: DevOpsAgentState = None) -> TestResult:
    # --- Step 0: Read test config from state ---
    config = state.repo_context.config if state and hasattr(state, 'repo_context') and hasattr(state.repo_context, 'config') else {}
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
        default_framework = "pytest"
    elif language == "node":
        test_file = os.path.join(repo_path, "autogen.test.js")
        default_cmd = ["npm", "test"]
        default_framework = "npm"
    elif language == "java":
        test_file = os.path.join(repo_path, "AutogenTest.java")
        default_cmd = ["mvn", "test"]
        default_framework = "maven"
    else:
        raise ValueError(f"[Test Agent] Unsupported language for testing: {language}")

    with open(test_file, "w") as f:
        f.write(test_code)

    logger.info(f"[Test Agent] Running tests using language: {language}")
    try:
        # Determine command to run
        run_cmd = None
        if command:
            if isinstance(command, str):
                run_cmd = command.split()
            else:
                run_cmd = command
        elif framework:
            if framework.lower() == "pytest":
                run_cmd = ["pytest", test_file]
            elif framework.lower() == "unittest":
                run_cmd = ["python", "-m", "unittest", test_file]
            elif framework.lower() == "npm":
                run_cmd = ["npm", "test"]
            elif framework.lower() == "maven" or framework.lower() == "mvn":
                run_cmd = ["mvn", "test"]
            elif framework.lower() == "junit":
                run_cmd = ["java", "-cp", repo_path, "org.junit.runner.JUnitCore", "AutogenTest"]
            elif framework.lower() == "gradle":
                run_cmd = ["./gradlew", "test"]
            else:
                logger.warning(f"[Test Agent] Unknown framework '{framework}', using default.")
                run_cmd = default_cmd
        else:
            run_cmd = default_cmd

        logger.info(f"[Test Agent] Running test command: {' '.join(run_cmd)}")
        result = subprocess.run(
            run_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True
        )

        passed = result.returncode == 0
        logs = result.stdout + result.stderr
        total, passed_count, failed_count = extract_test_results(logs, language)

        test_result = TestResult(
            passed=passed_count > 0 and failed_count == 0,
            logs=logs,
            total=total,
            coverage=None
        )

        # Publish TEST_RESULTS event if tests passed
        if test_result.passed:
            repo_name = os.path.basename(repo_path)
            event = TestResultsEvent(
                repo=repo_name,
                total_tests=total,
                passed=passed_count,
                failed=failed_count,
                coverage=None,
                logs=logs
            )
            publish_event(TEST_RESULTS, event.model_dump())
            logger.info(f"[Test Agent] TEST_RESULTS event published for repo: {repo_name}")

        return test_result

    except Exception as e:
        logger.error(f"[Test Agent] Error while running tests: {e}")
        return TestResult(False, str(e))
