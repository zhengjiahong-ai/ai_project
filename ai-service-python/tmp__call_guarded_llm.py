

def _call_guarded_llm(prompt: str, extra_system_instruction: str = "") -> str:
    return get_llm()._call(
        prompt,
        messages=build_guarded_messages(prompt, extra_system_instruction=extra_system_instruction),
    )


