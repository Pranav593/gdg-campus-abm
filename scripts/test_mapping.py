"""Run every mapping test in both graph folders, including integration builds."""
import subprocess
import sys
from pathlib import Path


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    for folder in ('utd-graph', 'src/mapping/utd-graph'):
        result = subprocess.run(
            [sys.executable, '-m', 'unittest', 'discover', '-s', str(root / folder), '-p', 'test_*.py'],
            cwd=root)
        if result.returncode:
            sys.exit(result.returncode)
