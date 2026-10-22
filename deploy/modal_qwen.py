"""NPC lab model on Modal (todo/25): Qwen/Qwen2.5-3B-Instruct, full precision, behind an OpenAI-compatible endpoint.

The organisers give competitors qwen2.5-3b-instruct (llm.legitreal.com); the lab uses the same open model as a stand-in
citizen, offline only (CLAUDE.md rule 2: analysis and testing that never touches the platform; Marc, 2026-10-22).
Nothing this model writes is posted.

    modal secret create swan-qwen-key API_KEY=<random>       # once; the same key goes in swan-ec2 .env as LAB_REMOTE_KEY
    modal deploy deploy/modal_qwen.py                        # prints the URL: put it in .env as LAB_REMOTE_URL (+ /v1)

One L4 GPU, scaled to zero after 5 idle minutes (Modal's free $30/month credit covers ~35 GPU hours).
"""
import os
import subprocess

import modal

MODEL = "Qwen/Qwen2.5-3B-Instruct"
SERVED = "qwen2.5-3b-instruct"

image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("vllm==0.10.1.1", "huggingface_hub[hf_transfer]==0.34.4")
         .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"}))
hf_cache = modal.Volume.from_name("swan-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("swan-vllm-cache", create_if_missing=True)
app = modal.App("swan-qwen")


@app.function(image=image, gpu="L4", scaledown_window=5 * 60, timeout=60 * 60,
              volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
              secrets=[modal.Secret.from_name("swan-qwen-key")])
@modal.concurrent(max_inputs=32)
@modal.web_server(port=8000, startup_timeout=15 * 60)
def serve():
    subprocess.Popen(["vllm", "serve", MODEL, "--served-model-name", SERVED, "--host", "0.0.0.0", "--port", "8000",
                      "--api-key", os.environ["API_KEY"], "--max-model-len", "8192",
                      "--gpu-memory-utilization", "0.90"])
