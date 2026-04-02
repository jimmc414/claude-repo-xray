"""
Tests for v3.2 scanner enhancements:
1. exec()/eval() security flagging
2. Silent failure pattern detection
3. Async/sync violation detection
4. Extended database query patterns + SQL string literals
5. Required vs optional env vars (or-fallback)
6. @deprecated marker scanning
"""

import ast
import sys
import os
import textwrap
from pathlib import Path

# Add lib to path
LIB_DIR = str(Path(__file__).parent.parent / "lib")
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from ast_analysis import (
    analyze_file, analyze_codebase, FileAnalysis,
    _detect_security_concern, _detect_silent_failure,
    _detect_async_violations, _detect_sql_strings,
)


# =============================================================================
# Helpers
# =============================================================================

def _analyze_source(source: str) -> FileAnalysis:
    """Analyze a source string by writing to a temp file."""
    import tempfile
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(source)
        f.flush()
        result = analyze_file(f.name)
    os.unlink(f.name)
    return result


def _analyze_source_codebase(source: str):
    """Analyze a source string through analyze_codebase."""
    import tempfile
    source = textwrap.dedent(source)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(source)
        f.flush()
        result = analyze_codebase([f.name])
    os.unlink(f.name)
    return result


# =============================================================================
# Enhancement 1: exec()/eval() Security Flagging
# =============================================================================

class TestSecurityConcerns:

    def test_exec_detected(self):
        result = _analyze_source("""
            exec("print('hello')")
        """)
        assert len(result.security_concerns) == 1
        assert result.security_concerns[0]["call"] == "exec"
        assert result.security_concerns[0]["category"] == "code_execution"

    def test_eval_detected(self):
        result = _analyze_source("""
            x = eval("1 + 2")
        """)
        assert len(result.security_concerns) == 1
        assert result.security_concerns[0]["call"] == "eval"

    def test_compile_detected(self):
        result = _analyze_source("""
            code = compile("x = 1", "<string>", "exec")
        """)
        assert len(result.security_concerns) == 1
        assert result.security_concerns[0]["call"] == "compile"

    def test_exec_not_cursor_execute(self):
        """cursor.execute() must NOT flag as security concern."""
        result = _analyze_source("""
            cursor.execute("SELECT * FROM users")
        """)
        assert len(result.security_concerns) == 0

    def test_exec_not_method_execute(self):
        """Any .execute() method must NOT flag."""
        result = _analyze_source("""
            session.execute("query")
            engine.execute("sql")
        """)
        assert len(result.security_concerns) == 0

    def test_multiple_security_concerns(self):
        result = _analyze_source("""
            exec(user_input)
            eval(user_input)
        """)
        assert len(result.security_concerns) == 2

    def test_codebase_aggregation(self):
        results = _analyze_source_codebase("""
            exec("code")
            eval("expr")
        """)
        sc = results.get("security_concerns", {})
        total = sum(len(v) for v in sc.values())
        assert total == 2


# =============================================================================
# Enhancement 2: Silent Failure Pattern Detection
# =============================================================================

class TestSilentFailures:

    def test_except_pass(self):
        result = _analyze_source("""
            try:
                x = 1
            except Exception:
                pass
        """)
        assert len(result.silent_failures) == 1
        sf = result.silent_failures[0]
        assert sf["pattern"] == "except_pass"
        assert sf["except_type"] == "broad"

    def test_bare_except_pass(self):
        result = _analyze_source("""
            try:
                x = 1
            except:
                pass
        """)
        assert len(result.silent_failures) == 1
        assert result.silent_failures[0]["except_type"] == "bare"

    def test_log_and_swallow(self):
        result = _analyze_source("""
            try:
                x = 1
            except Exception as e:
                logging.error(e)
        """)
        assert len(result.silent_failures) == 1
        assert result.silent_failures[0]["pattern"] == "log_and_swallow"

    def test_print_and_swallow(self):
        result = _analyze_source("""
            try:
                x = 1
            except Exception as e:
                print(e)
        """)
        assert len(result.silent_failures) == 1
        assert result.silent_failures[0]["pattern"] == "log_and_swallow"

    def test_no_false_positive_reraise(self):
        """except that re-raises should NOT be flagged as silent."""
        result = _analyze_source("""
            try:
                x = 1
            except ValueError:
                raise
        """)
        assert len(result.silent_failures) == 0

    def test_no_false_positive_specific_except(self):
        """Specific exception with real handling body should not flag."""
        result = _analyze_source("""
            try:
                x = 1
            except ValueError:
                x = default_value
                do_something()
        """)
        assert len(result.silent_failures) == 0

    def test_base_exception_flagged(self):
        result = _analyze_source("""
            try:
                x = 1
            except BaseException:
                pass
        """)
        assert len(result.silent_failures) == 1
        assert result.silent_failures[0]["except_type"] == "broad"


# =============================================================================
# Enhancement 3: Async/Sync Violation Detection
# =============================================================================

class TestAsyncViolations:

    def test_time_sleep_in_async(self):
        result = _analyze_source("""
            import time
            async def my_func():
                time.sleep(1)
        """)
        assert len(result.async_violations) == 1
        assert result.async_violations[0]["violation_type"] == "blocking_sleep"
        assert result.async_violations[0]["function"] == "my_func"

    def test_requests_in_async(self):
        result = _analyze_source("""
            import requests
            async def fetch_data():
                requests.get("http://example.com")
        """)
        assert len(result.async_violations) == 1
        assert result.async_violations[0]["violation_type"] == "blocking_http"

    def test_run_until_complete_in_async(self):
        result = _analyze_source("""
            async def bad_func():
                loop.run_until_complete(coro())
        """)
        assert len(result.async_violations) == 1
        assert result.async_violations[0]["violation_type"] == "nested_event_loop"

    def test_time_sleep_in_sync_no_violation(self):
        """time.sleep in a sync function is perfectly fine."""
        result = _analyze_source("""
            import time
            def my_func():
                time.sleep(1)
        """)
        assert len(result.async_violations) == 0

    def test_multiple_violations_same_function(self):
        result = _analyze_source("""
            import time, requests
            async def bad_func():
                time.sleep(1)
                requests.post("http://example.com")
        """)
        assert len(result.async_violations) == 2

    def test_codebase_async_violations_aggregated(self):
        results = _analyze_source_codebase("""
            import time
            async def my_func():
                time.sleep(1)
        """)
        violations = results.get("async_patterns", {}).get("violations", [])
        assert len(violations) == 1


# =============================================================================
# Enhancement 4: Extended Database Query Patterns + SQL Strings
# =============================================================================

class TestDatabasePatterns:

    def test_filter_detected_as_db(self):
        result = _analyze_source("""
            queryset.filter(name="test")
        """)
        db_effects = [se for se in result.side_effects if se["category"] == "db"]
        assert len(db_effects) >= 1

    def test_filter_by_detected(self):
        result = _analyze_source("""
            User.query.filter_by(active=True)
        """)
        db_effects = [se for se in result.side_effects if se["category"] == "db"]
        assert len(db_effects) >= 1

    def test_objects_get_detected(self):
        result = _analyze_source("""
            User.objects.get(id=1)
        """)
        db_effects = [se for se in result.side_effects if se["category"] == "db"]
        assert len(db_effects) >= 1

    def test_session_execute_detected(self):
        result = _analyze_source("""
            session.execute(text("SELECT 1"))
        """)
        db_effects = [se for se in result.side_effects if se["category"] == "db"]
        assert len(db_effects) >= 1

    def test_sql_string_select(self):
        result = _analyze_source("""
            query = "SELECT id FROM users WHERE active = 1"
        """)
        assert len(result.sql_strings) == 1
        assert "SELECT" in result.sql_strings[0]["query"]

    def test_sql_string_insert(self):
        result = _analyze_source("""
            sql = "INSERT INTO logs (msg) VALUES (?)"
        """)
        assert len(result.sql_strings) == 1

    def test_sql_string_cypher(self):
        result = _analyze_source("""
            q = "MATCH (n:Person) RETURN n.name"
        """)
        assert len(result.sql_strings) == 1

    def test_no_false_positive_short_string(self):
        """Short strings should not be flagged."""
        result = _analyze_source("""
            x = "hello"
        """)
        assert len(result.sql_strings) == 0

    def test_no_false_positive_select_in_prose(self):
        """Plain English with 'select' should not match."""
        result = _analyze_source("""
            msg = "Please select an option from the menu"
        """)
        assert len(result.sql_strings) == 0


# =============================================================================
# Enhancement 5: Required vs Optional Env Vars (or-fallback)
# =============================================================================

class TestEnvVarFallback:

    def test_or_fallback_makes_optional(self):
        """os.getenv('X') or 'y' should be required=False."""
        import tempfile
        source = textwrap.dedent("""
            import os
            DB_HOST = os.getenv('DB_HOST') or 'localhost'
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source)
            f.flush()
            from gap_features import _extract_env_vars_from_file_ast
            env_vars = _extract_env_vars_from_file_ast(f.name)
        os.unlink(f.name)

        assert len(env_vars) == 1
        assert env_vars[0]["variable"] == "DB_HOST"
        assert env_vars[0]["required"] is False
        assert env_vars[0]["fallback_type"] == "or_fallback"

    def test_explicit_default_optional(self):
        """os.getenv('X', 'y') should be required=False with explicit_default."""
        import tempfile
        source = textwrap.dedent("""
            import os
            PORT = os.getenv('PORT', '8080')
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source)
            f.flush()
            from gap_features import _extract_env_vars_from_file_ast
            env_vars = _extract_env_vars_from_file_ast(f.name)
        os.unlink(f.name)

        assert len(env_vars) == 1
        assert env_vars[0]["required"] is False
        assert env_vars[0]["fallback_type"] == "explicit_default"

    def test_no_default_required(self):
        """os.getenv('X') with no fallback should be required=True."""
        import tempfile
        source = textwrap.dedent("""
            import os
            SECRET = os.getenv('SECRET_KEY')
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source)
            f.flush()
            from gap_features import _extract_env_vars_from_file_ast
            env_vars = _extract_env_vars_from_file_ast(f.name)
        os.unlink(f.name)

        assert len(env_vars) == 1
        assert env_vars[0]["required"] is True
        assert env_vars[0]["fallback_type"] == "none"

    def test_or_fallback_no_double_count(self):
        """os.getenv('X') or 'y' should not be counted twice."""
        import tempfile
        source = textwrap.dedent("""
            import os
            VAL = os.getenv('MY_VAR') or 'default'
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source)
            f.flush()
            from gap_features import _extract_env_vars_from_file_ast
            env_vars = _extract_env_vars_from_file_ast(f.name)
        os.unlink(f.name)

        assert len(env_vars) == 1


# =============================================================================
# Enhancement 6: @deprecated Marker Scanning
# =============================================================================

class TestDeprecationMarkers:

    def test_deprecated_decorator_function(self):
        result = _analyze_source("""
            @deprecated
            def old_function():
                pass
        """)
        assert len(result.deprecation_markers) == 1
        assert result.deprecation_markers[0]["name"] == "old_function"
        assert result.deprecation_markers[0]["kind"] == "function"

    def test_deprecated_decorator_class(self):
        result = _analyze_source("""
            @deprecated
            class OldClass:
                pass
        """)
        assert len(result.deprecation_markers) == 1
        assert result.deprecation_markers[0]["name"] == "OldClass"
        assert result.deprecation_markers[0]["kind"] == "class"

    def test_comment_deprecation_in_tech_debt(self):
        """Comment-based deprecation should be detected by tech_debt_analysis."""
        import tempfile
        source = textwrap.dedent("""
            # deprecated: use new_function instead
            def old_function():
                pass
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source)
            f.flush()
            from tech_debt_analysis import analyze_tech_debt
            result = analyze_tech_debt([f.name])
        os.unlink(f.name)

        assert len(result["deprecations"]) >= 1
        assert result["deprecations"][0]["source"] == "comment"

    def test_deprecation_warning_detected(self):
        """warnings.warn with deprecation should be detected."""
        import tempfile
        source = textwrap.dedent("""
            import warnings
            warnings.warn("This is deprecated", DeprecationWarning)
        """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(source)
            f.flush()
            from tech_debt_analysis import analyze_tech_debt
            result = analyze_tech_debt([f.name])
        os.unlink(f.name)

        assert len(result["deprecations"]) >= 1

    def test_no_false_positive_regular_decorator(self):
        """@property, @staticmethod etc. should NOT flag as deprecation."""
        result = _analyze_source("""
            @property
            def name(self):
                return self._name
        """)
        assert len(result.deprecation_markers) == 0


# =============================================================================
# Regression: Existing detections still work
# =============================================================================

class TestRegressionExistingDetections:

    def test_existing_side_effects_preserved(self):
        """Existing side effect patterns should still be detected."""
        result = _analyze_source("""
            import subprocess
            subprocess.run(["ls"])
        """)
        assert any(se["category"] == "subprocess" for se in result.side_effects)

    def test_existing_file_side_effect(self):
        result = _analyze_source("""
            import json
            json.dump(data, fp)
        """)
        assert any(se["category"] == "file" for se in result.side_effects)

    def test_to_dict_has_new_keys(self):
        """to_dict() should include all new fields."""
        result = _analyze_source("x = 1")
        d = result.to_dict()
        for key in ["security_concerns", "silent_failures", "async_violations",
                     "sql_strings", "deprecation_markers"]:
            assert key in d, f"Missing key: {key}"

    def test_self_analysis_no_crash(self):
        """Run scanner on its own source — must not crash."""
        project_dir = Path(__file__).parent.parent
        py_files = list(project_dir.glob("lib/*.py"))
        assert len(py_files) > 0

        results = analyze_codebase(py_files[:5])

        # Basic structure checks
        assert "files" in results
        assert "summary" in results
        assert "security_concerns" in results
        assert "silent_failures" in results
        assert "sql_strings" in results
        assert "deprecation_markers" in results
        assert isinstance(results["async_patterns"], dict)
