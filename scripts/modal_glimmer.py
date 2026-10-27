"""Prepared deployment. Not run during the key-free build.

Install modal, configure its account and a named Secret `apprentice-glimmer` with
GLIMMER_API_KEY (and HF_TOKEN if weights are gated), then explicitly:
  modal deploy scripts/modal_glimmer.py
The 80 GB GPU incurs provider charges when started. Scale-to-zero after 60s.
"""

import os
import subprocess

import modal

app = modal.App("apprentice-glimmer")
image = modal.Image.from_registry("vllm/vllm-openai:muse-glimmer", add_python="3.11")
volume = modal.Volume.from_name("apprentice-glimmer-weights", create_if_missing=True)


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=1200,
    scaledown_window=60,
    max_containers=1,
    volumes={"/root/.cache/huggingface": volume},
    secrets=[modal.Secret.from_name("apprentice-glimmer")],
)
@modal.web_server(8000, startup_timeout=1100)
def serve() -> None:
    if not os.environ.get("GLIMMER_API_KEY"):
        raise RuntimeError("Configure the apprentice-glimmer Modal Secret first")
    subprocess.Popen(
        [
            "vllm",
            "serve",
            "meta-models/Muse-Glimmer-30B",
            "--served-model-name",
            "muse-glimmer",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--max-model-len",
            "8300",
            "--enforce-eager",
            "--enable-auto-tool-choice",
            "--tool-call-parser",
            "muse_glimmer",
            "--reasoning-parser",
            "muse_glimmer",
            "--generation-config",
            "auto",
            "--api-key",
            os.environ["GLIMMER_API_KEY"],
        ]
    )
