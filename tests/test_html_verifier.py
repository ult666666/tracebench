"""The real verifier must enforce the sample's byte-level contract."""

import contextlib
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import verify_html

ROOT = Path(__file__).resolve().parents[1]


class HtmlVerifierTests(unittest.TestCase):
    def test_sample_bytes_accept_lf_and_reject_changed_crlf(self):
        # Use the actual CLI in child processes while substituting a temporary
        # fixture root, so this regression never rewrites the committed sample.
        executable = [sys.executable, "-c", "import sys; sys.path.insert(0, " + repr(str(ROOT))
                      + "); from tracebench.cli import main; raise SystemExit(main())"]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shutil.copytree(ROOT / "fixtures", directory / "fixtures")
            (directory / "docs").mkdir()
            artifacts = directory / "artifacts"
            artifacts.mkdir()
            with patch.object(verify_html, "ROOT", directory), contextlib.redirect_stdout(io.StringIO()):
                expected = verify_html.sample_report().encode("utf-8")
                sample = directory / "docs/sample-report.html"
                sample.write_bytes(expected)
                verify_html.verify(artifacts, executable)
                different = expected.replace(b"\n", b"\r\n")
                self.assertNotEqual(different, expected)
                sample.write_bytes(different)
                with self.assertRaisesRegex(AssertionError, "Regenerate sample"):
                    verify_html.verify(artifacts, executable)


if __name__ == "__main__":
    unittest.main()
