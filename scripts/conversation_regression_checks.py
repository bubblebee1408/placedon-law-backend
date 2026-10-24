"""Expose conversation regressions to the repository's counted offline gate."""
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

def main():
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_conversation_reliability.py")
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_vault_catalog.py"))
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_document_evidence.py"))
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_actor_document_cache.py"))
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_worker_actor_identity.py"))
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_draft_review_integrity.py"))
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_document_coverage.py"))
    suite.addTests(unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_document_search_intent.py"))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    failed = len(result.failures) + len(result.errors)
    passed = result.testsRun - failed - len(result.skipped)
    print(f"\n{passed}/{result.testsRun} passed")
    return int(failed > 0 or bool(result.skipped) or result.testsRun == 0)

if __name__ == "__main__":
    raise SystemExit(main())
