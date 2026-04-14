import sys
import os

# Ensure the project root is on sys.path so `import extract_jobs` and
# `import app` work regardless of where pytest is invoked from.
sys.path.insert(0, os.path.dirname(__file__))
