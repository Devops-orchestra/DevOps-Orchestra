import re

def parse_llm_summary(text: str) -> dict:
    errors = []
    warnings = []
    passed = True
    notes = []

    current_section = None
    for line in text.strip().splitlines():
        line = line.strip()

        if line.lower().startswith("errors"):
            current_section = "errors"
            passed = False
        elif line.lower().startswith("warnings"):
            current_section = "warnings"
        elif line.lower().startswith("notes"):
            current_section = "notes"
        elif line.startswith("-"):
            description = line.lstrip("-").strip()
            if current_section == "errors":
                errors.append(description)
            elif current_section == "warnings":
                warnings.append(description)
            elif current_section == "notes":
                notes.append(description)

    return {
        "passed": passed if not errors else False,
        "errors": errors,
        "warnings": warnings,
        "notes": notes
    }
