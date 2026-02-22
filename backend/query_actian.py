import sys
import os

from cortex import CortexClient, DistanceMetric

URL = os.environ.get("ACTIAN_VECTORAI_URL", "http://localhost:8000") 
# wait, main.py gets it from settings.actian_vectorai_url
