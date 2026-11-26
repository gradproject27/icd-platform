"""Event confidence for risk-v1 (design section 9A.2): the classifier part (step 4).

`features` defines what the classifier sees, `prepare` turns NetFlow v3 CSVs into split and
sampled arrays, `train` fits, calibrates and evaluates, `metrics` holds the measures. Training
runs on HPC or a laptop with requirements-dev.txt (scikit-learn, pyarrow); the API image does
not import this package yet (step 6 adds scoring).
"""
