import os
import re
import subprocess
from jinja2 import Template
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.llm_config.model_wrapper import run_prompt

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

def run_tests_for_language(repo_path: str, test_code: str) -> TestResult:
    language = detect_language(repo_path)

    if language == "python":
        test_file = os.path.join(repo_path, "autogen_tests.py")
    elif language == "node":
        test_file = os.path.join(repo_path, "autogen.test.js")
    elif language == "java":
        test_file = os.path.join(repo_path, "AutogenTest.java")
    else:
        raise ValueError(f"[Test Agent] Unsupported language for testing: {language}")

    with open(test_file, "w") as f:
        f.write(test_code)

    logger.info(f"[Test Agent] Running tests using language: {language}")
    try:
        if language == "python":
            result = subprocess.run(
                ["pytest", test_file],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
        elif language == "node":
            result = subprocess.run(
                ["npm", "test"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
        elif language == "java":
            # Try Maven first
            if os.path.exists(os.path.join(repo_path, "pom.xml")):
                result = subprocess.run(
                    ["mvn", "test"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
            # Try Gradle next
            elif os.path.exists(os.path.join(repo_path, "build.gradle")):
                result = subprocess.run(
                    ["./gradlew", "test"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
            else:
                raise ValueError("Java project detected, but neither Maven nor Gradle build file was found.")

        passed = result.returncode == 0
        logs = result.stdout + result.stderr
        total, passed_count, failed_count = extract_test_results(logs, language)

        return TestResult(
            passed=passed_count > 0 and failed_count == 0,
            logs=logs,
            total=total,
            coverage=None
        )

    except Exception as e:
        logger.error(f"[Test Agent] Error while running tests: {e}")
        return TestResult(False, str(e))
