"""
DevOps Orchestra entry point. Runs the coordinator daemon (Slack gateway + pipeline).
Trigger the pipeline from Slack (e.g. "Run pipeline for branch main"); 
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coordinator.main import main

if __name__ == "__main__":
    main()
