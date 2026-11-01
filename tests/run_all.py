"""Run every test. No internet needed. Usage: python tests/run_all.py"""
import glob, os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__)); bad = []
for t in sorted(glob.glob(os.path.join(here, 'test_*.py'))):
    r = subprocess.run([sys.executable, t], capture_output=True, text=True); ok = r.returncode == 0
    print(('PASS ' if ok else 'FAIL ') + os.path.basename(t))
    if not ok: bad.append(t); print(r.stdout[-1500:] + r.stderr[-1500:])
print('\nALL TEST FILES PASSED' if not bad else f'\n{len(bad)} test file(s) failed'); sys.exit(1 if bad else 0)
