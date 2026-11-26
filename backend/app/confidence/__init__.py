"""Event confidence for risk-v1 (design section 9A.2): classifier (step 4), LLM (step 5), stacker.

`features` defines what the classifier sees, `prepare` turns NetFlow v3 CSVs into split and
sampled arrays, `train` fits, calibrates and evaluates, `metrics` holds the measures. Training
runs on HPC or a laptop with requirements-dev.txt (scikit-learn, pyarrow). `groups` and
`llm_opinion` / `llm_calibrate` give p_llm, `stack` combines both into C. The API and worker
images import only `values` (no NumPy), through app.correlation.risk.
"""
