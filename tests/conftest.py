"""Tests never call a real model: pin the agent settings before the app reads .env."""

import os

os.environ["FOUNDRY_PROJECT_ENDPOINT"] = ""
os.environ["REPLAY_MODE"] = "0"
os.environ["RECORD_REPLAY"] = "0"
