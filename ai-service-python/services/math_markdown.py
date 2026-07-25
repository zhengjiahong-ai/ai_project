MATH_MARKDOWN_GUIDELINE = """
When mathematical symbols, equations, or derivations appear in your answer, you must format them as standard Markdown LaTeX.
- Inline math must use $...$
- Display equations must use $$...$$
- Do not use \\( ... \\) or \\[ ... \\] delimiters
- Never output raw formula fragments like x_t^i, T_t, _{i=1}, \\sum, or \\frac without math delimiters
- If a formula appears inside a Chinese sentence, only wrap the formula fragment itself
- Preferred examples:
  - $x_t^i$
  - $T_t = \\{(x_t^i, y_t^i)\\}_{i=1}^{|T_t|}$
  - $$L = \\frac{1}{N}\\sum_{i=1}^{N} \\ell(x_i, y_i)$$
""".strip()
