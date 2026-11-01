"""Run the real frontend month-transition regression tests under Node."""
import os
from pathlib import Path
import subprocess
import unittest

class MonthRolloverTests(unittest.TestCase):
    def test_frontend_calendar_and_missing_data_cases(self):
        root=Path(__file__).resolve().parents[1]
        run=subprocess.run(['node',str(root/'tests/test_month_rollover.js')],env={**os.environ,'EVN_COMPONENT':str(root/'custom_components/evn')},capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
