"""Test environment: offline JPL kernel, a throwaway data directory, a small fast search."""
import os
import tempfile

os.environ["EPHEMERIS_SOURCE"] = "de421"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="probe-test-")
os.environ["SEARCH_HORIZON_DAYS"] = "800"
os.environ["SEARCH_WORKERS"] = "1"
os.environ["SEARCH_MAXITER"] = "120"
os.environ["ANTHROPIC_API_KEY"] = ""
