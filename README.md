# CSA LLM Evaluation

Standalone 3-layer evaluation framework for CXOne agentic analytics APIs (summary, topics, insights-recommendations).

## Setup

```bash
pip install -e ".[test]"
cp .env.test .env          # populate with credentials
```

## Run

```bash
pytest -m layer1 -v        # deterministic rules
pytest -m layer2 -v        # LLM-as-judge (requires AWS_PROFILE)
pytest -m layer3 -v        # prompt rules (requires AWS_PROFILE)
python dashboard/server.py # live dashboard
```
