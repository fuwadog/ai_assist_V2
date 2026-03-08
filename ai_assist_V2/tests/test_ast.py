from __future__ import annotations

from tools.ast_summarizer import ASTSummarizer


def test_python_summarization(temp_dir):
    src = """
\"\"\"A mock python file.\"\"\"

import os
from collections import defaultdict

class MyClass(object):
    \"\"\"Does class things.\"\"\"
    def do_stuff(self, a: int) -> bool:
        \"\"\"Return true.\"\"\"
        return True

def top_level():
    pass
    """
    path = temp_dir / "mock.py"
    path.write_text(src)
    
    summarizer = ASTSummarizer()
    summary = summarizer.summarize(path)
    
    assert "A mock python file." in summary
    assert "import os" in summary
    assert "class MyClass(object)" in summary
    assert "Does class things." in summary
    assert "def do_stuff(self, a: int) -> bool" in summary
    assert "def top_level()" in summary


def test_fallback_summarization(temp_dir):
    path = temp_dir / "data.csv"
    path.write_text("a,b,c\n1,2,3")
    
    summarizer = ASTSummarizer()
    res = summarizer.summarize(path)
    assert "data.csv (raw, truncated)" in res
    assert "1,2,3" in res
