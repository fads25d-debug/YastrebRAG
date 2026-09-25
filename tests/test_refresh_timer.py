"""The UI refresh timer must not import the model's numerical stack."""
import ast
import builtins
from pathlib import Path

from streamlit.time_util import time_to_seconds


def test_refresh_timer_works_while_numpy_is_initializing(monkeypatch):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8'))
    refresh = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == 'refresh_answers')
    interval = next(kw.value for kw in refresh.decorator_list[0].keywords
                    if kw.arg == 'run_every')
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in ('numpy', 'pandas'):
            raise ImportError('Numerical stack is still initializing in the answer worker')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    for active, expected in ((True, 1.0), (False, None)):
        value = eval(compile(ast.Expression(interval), '<refresh interval>', 'eval'),
                     {'active_jobs': active})
        assert time_to_seconds(value, coerce_none_to_inf=False) == expected
