from shared_modules.llm_config.model_wrapper import run_prompt

def call_llm_with_code_context(prompt: str, context: str) -> str:
    full_prompt = prompt + "\n\n---\nProject Files:\n" + context
    return run_prompt(full_prompt)
