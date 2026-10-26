"""Run prompt v0 on evidence packages and write the model-run and performance record (AI1).

It records what the AI1 task asks: did the model run, load time, inference time, resources,
errors and limits, and whether each answer becomes a valid AnalysisReport (backend/app/analysis).

Backends
  stub          no model; returns the hand-written sample output. Tests the harness only.
  openai_http   any OpenAI-compatible server (vLLM, llama.cpp server, Ollama /v1): --endpoint URL
  transformers  weights loaded in this process (GPU or CPU); needs torch and transformers

Run from the repo root:
  python tools/ai1/bench.py --backend stub --out tools/ai1/runs/stub
  python tools/ai1/bench.py --backend transformers --model /scratch/$USER/models/<dir> \
      --revision <commit> --licence-note "<licence>, <card URL>, checked <date>" --out runs/<name>

Needs pydantic (as pinned in backend/requirements.txt); psutil is optional.
"""

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from app.analysis import PROMPT_VERSION, ReportMeta, build_messages, run_analysis  # noqa: E402
from app.contracts import EvidencePackage  # noqa: E402

try:
    import psutil
except ImportError:  # the record still works, without RAM figures
    psutil = None

SAMPLE_PACKAGE = HERE / "samples" / "evidence-inc-ai1-0001.json"
SAMPLE_OUTPUT = HERE / "samples" / "llm-output-good-inc-ai1-0001.json"
TARGET_SECONDS = 30  # NFR-P-05


def gpu_used_mb() -> float | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return sum(float(x) for x in out) if out else None


class Sampler(threading.Thread):
    """Samples process RAM and GPU memory every 0.5 s."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop_flag = threading.Event()
        self.peak_rss_mb = None
        self.peak_gpu_mb = None
        self.proc = psutil.Process() if psutil else None

    def run(self):
        while not self.stop_flag.is_set():
            if self.proc:
                self.peak_rss_mb = max(self.peak_rss_mb or 0, self.proc.memory_info().rss / 1e6)
            gpu = gpu_used_mb()
            if gpu is not None:
                self.peak_gpu_mb = max(self.peak_gpu_mb or 0, gpu)
            self.stop_flag.wait(0.5)

    def stop(self):
        self.stop_flag.set()
        self.join(timeout=2)


def environment() -> dict:
    env = {
        "time_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "ram_total_gb": round(psutil.virtual_memory().total / 1e9, 1) if psutil else None,
        "scheduler_job": {
            k: os.environ[k]
            for k in ("SLURM_JOB_ID", "SLURM_JOB_PARTITION", "PBS_JOBID", "LSB_JOBID")
            if k in os.environ
        },
        "gpus": None,
    }
    if shutil.which("nvidia-smi"):
        fields = "--query-gpu=name,memory.total,driver_version"
        query = ["nvidia-smi", fields, "--format=csv,noheader"]
        try:
            out = subprocess.run(query, capture_output=True, text=True, timeout=5).stdout
            env["gpus"] = out.strip().splitlines()
        except (OSError, subprocess.SubprocessError):
            pass
    from importlib.metadata import PackageNotFoundError, version

    for name in ("torch", "transformers", "pydantic", "vllm"):
        try:
            env[name] = version(name)
        except PackageNotFoundError:
            pass
    return env


class Stub:
    def __init__(self, args):
        self.model_name, self.revision = "stub (no model)", "n/a"

    def load(self):
        pass

    def generate(self, messages, max_new_tokens, temperature):
        return SAMPLE_OUTPUT.read_text(encoding="utf-8"), {}


class OpenAIHTTP:
    def __init__(self, args):
        self.url, self.model_name = args.endpoint, args.model
        self.revision = args.revision or "server-side: record it by hand"
        self.key = os.environ.get("OPENAI_API_KEY", "none")

    def load(self):
        pass  # the server loads the model; note its start-up time by hand

    def generate(self, messages, max_new_tokens, temperature):
        body = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"}
        request = urllib.request.Request(self.url, json.dumps(body).encode(), headers)
        with urllib.request.urlopen(request, timeout=600) as response:
            data = json.load(response)
        usage = data.get("usage", {})
        return data["choices"][0]["message"]["content"], {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }


class HFTransformers:
    def __init__(self, args):
        self.args, self.model_name = args, args.model
        self.revision = args.revision or "not given: record the commit hash by hand"

    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        local = Path(self.args.model).exists()
        kwargs = {} if local or not self.args.revision else {"revision": self.args.revision}
        self.tok = AutoTokenizer.from_pretrained(self.args.model, **kwargs)
        if self.args.load_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        else:
            kwargs["torch_dtype"] = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        if torch.cuda.is_available():
            kwargs["device_map"] = "auto"
        self.model = AutoModelForCausalLM.from_pretrained(self.args.model, **kwargs)
        self.torch = torch

    def generate(self, messages, max_new_tokens, temperature):
        ids = self.tok.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(self.model.device)
        with self.torch.no_grad():
            out = self.model.generate(
                ids,
                max_new_tokens=max_new_tokens,
                do_sample=temperature > 0,
                temperature=temperature if temperature > 0 else None,
            )
        new = out[0][ids.shape[1] :]
        return self.tok.decode(new, skip_special_tokens=True), {
            "prompt_tokens": int(ids.shape[1]),
            "completion_tokens": int(new.shape[0]),
        }


BACKENDS = {"stub": Stub, "openai_http": OpenAIHTTP, "transformers": HFTransformers}


def run_one(backend, args, path: Path, run: int, out: Path) -> dict:
    evidence = EvidencePackage.model_validate_json(path.read_text(encoding="utf-8"))
    record: dict = {"package": path.name, "run": run}
    start = time.perf_counter()
    text, usage = backend.generate(build_messages(evidence), args.max_new_tokens, args.temperature)
    record["infer_seconds"] = round(time.perf_counter() - start, 2)
    record.update({k: v for k, v in usage.items() if v is not None})
    if usage.get("completion_tokens") and record["infer_seconds"]:
        record["tokens_per_second"] = round(usage["completion_tokens"] / record["infer_seconds"], 1)
    (out / f"output_{path.stem}_run{run}.txt").write_text(text, encoding="utf-8")
    meta = ReportMeta(
        report_id=f"bench-{path.stem}-{run}"[:128],
        generated_at=datetime.now(UTC),
        generated_by="mock" if args.backend == "stub" else args.site,
        model_id=backend.model_name,
    )
    result = run_analysis(text, evidence, meta)
    record["valid_analysis"] = result.valid
    record["failed_checks"] = sorted({p.check for p in result.problems()})
    record["problems"] = [f"{p.check} {p.location}: {p.detail}" for p in result.problems()][:10]
    if result.grounding:
        record["grounding_rate"] = round(result.grounding.grounding_rate, 3)
        record["ungrounded"] = [f"{p.location}: {p.detail}" for p in result.grounding.ungrounded]
    if result.report:
        record["confidence"] = result.report.confidence
        record["attack_type"] = result.report.attack_type
    return record


def render_md(rec: dict) -> str:
    m, env, load, res = rec["model"], rec["environment"], rec["load"], rec["resources"]
    runs = rec["runs"]
    times = [r["infer_seconds"] for r in runs if "infer_seconds" in r]
    tps = [r["tokens_per_second"] for r in runs if "tokens_per_second" in r]
    valid = [r for r in runs if r.get("valid_analysis")]
    attack_types = sorted({str(r.get("attack_type")) for r in valid})
    if m["backend"] == "stub":
        target = "n/a (stub, no model)"
    elif times:
        target = "met" if max(times) <= TARGET_SECONDS else "NOT met"
    else:
        target = "not measured"
    gpu = f"{res['peak_gpu_mb']:.0f} MB" if res["peak_gpu_mb"] is not None else "no GPU seen"
    ram = f"{res['peak_rss_mb']:.0f} MB" if res["peak_rss_mb"] is not None else "n/a (no psutil)"
    lines = [
        "# Model-run and performance record",
        "",
        f"- Date (UTC): {env['time_utc']}",
        f"- Host: {env['host']} | CPUs: {env['cpu_count']} | RAM: {env['ram_total_gb']} GB"
        f" | GPUs: {env['gpus']}",
        f"- Scheduler job: {env['scheduler_job'] or 'none (interactive or local)'}",
        f"- Model: {m['name']} | revision: {m['revision']} | backend: {m['backend']}"
        f" | quantization: {m['quantization']}",
        f"- Licence: {m['licence_note']}",
        f"- Prompt: {m['prompt_version']} | temperature: {m['temperature']}",
        "",
        "| Question | Answer |",
        "| --- | --- |",
        f"| Did the model load? | {'yes' if load.get('ok') else 'NO'} |",
        f"| Load time | {load.get('seconds')} s |",
        f"| Runs | {len(runs)} |",
        f"| Inference time (median / max) | "
        f"{round(statistics.median(times), 2) if times else 'n/a'} s / "
        f"{max(times) if times else 'n/a'} s |",
        f"| Tokens per second (median) | {round(statistics.median(tps), 1) if tps else 'n/a'} |",
        f"| Peak process RAM | {ram} |",
        f"| Peak GPU memory used | {gpu} |",
        f"| Valid analyses (parse + grounding + contract) | {len(valid)} of {len(runs)} |",
        f"| Attack types across valid runs | {', '.join(attack_types) or 'n/a'} |",
        f"| Inference within {TARGET_SECONDS} s (NFR-P-05) | {target} |",
        "",
    ]
    fails: dict[str, int] = {}
    for r in runs:
        for check in r.get("failed_checks", []):
            fails[check] = fails.get(check, 0) + 1
    summary = ", ".join(f"{c} x{n}" for c, n in sorted(fails.items())) or "none"
    lines.append(f"Failed checks across runs: {summary}")
    if rec["errors"]:
        lines += ["", "Errors:"] + [f"- {e}" for e in rec["errors"]]
    lines += [
        "",
        "The stub backend measures the harness only. For openai_http, note the server start-up"
        " time by hand as the load time. Fill the licence line from the model card before use.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--backend", choices=BACKENDS, default="stub")
    ap.add_argument("--model", default="stub")
    ap.add_argument("--revision", default=None, help="weights commit hash")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8000/v1/chat/completions")
    ap.add_argument("--site", choices=("hpc", "local"), default="hpc", help="where the model ran")
    ap.add_argument("--load-4bit", action="store_true")
    ap.add_argument("--packages", nargs="+", type=Path, default=[SAMPLE_PACKAGE])
    ap.add_argument("--runs", type=int, default=3, help="runs per package (plan: at least 3)")
    ap.add_argument("--max-new-tokens", type=int, default=3000)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--licence-note", default="NOT CHECKED: read the model card first")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    backend = BACKENDS[args.backend](args)
    rec: dict = {
        "environment": environment(),
        "model": {
            "name": backend.model_name,
            "revision": backend.revision,
            "backend": args.backend,
            "quantization": "4-bit" if args.load_4bit else "none",
            "licence_note": args.licence_note,
            "prompt_version": PROMPT_VERSION,
            "temperature": args.temperature,
        },
        "load": {},
        "runs": [],
        "errors": [],
    }
    sampler = Sampler()
    sampler.start()
    start = time.perf_counter()
    try:
        backend.load()
        rec["load"] = {"ok": True, "seconds": round(time.perf_counter() - start, 2)}
    except Exception as exc:  # the model did not start: this is the blocker evidence
        rec["load"] = {"ok": False, "seconds": round(time.perf_counter() - start, 2)}
        rec["errors"].append(f"load: {type(exc).__name__}: {exc}")

    if rec["load"]["ok"]:
        for path in args.packages:
            for run in range(1, args.runs + 1):
                try:
                    rec["runs"].append(run_one(backend, args, path, run, args.out))
                except Exception as exc:  # recorded, never fatal
                    error = f"{path.name} run {run}: {type(exc).__name__}: {exc}"
                    rec["errors"].append(error)
                    rec["runs"].append({"package": path.name, "run": run, "error": error})
    sampler.stop()
    rec["resources"] = {"peak_rss_mb": sampler.peak_rss_mb, "peak_gpu_mb": sampler.peak_gpu_mb}

    text = render_md(rec)
    (args.out / "model_run_record.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    (args.out / "model_run_record.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if rec["load"]["ok"] and not rec["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
