"""Reference solution.

Train a LoRA adapter of Qwen3-8B on data/train.jsonl with the SFT trainer of TRL. Week 25.

On the pod (one 48 GB GPU, in the folder of the repository):

    pip install -r train/requirements.txt
    python train/train_lora.py --output /workspace/adapter

On your Mac, before you rent the GPU:

    make train-smoke

The smoke mode trains a tiny model with the same architecture (Qwen3) for a few steps on the
CPU, on the first examples of data/train.jsonl. It needs no GPU and about a minute, and it finds
the errors of your settings and of your data before they cost money. Its adapter goes to
train/smoke-adapter/ (do not commit it).

The adapter is the folder of --output: adapter_config.json and adapter_model.safetensors. vLLM
serves it beside the base model with --enable-lora --lora-modules <name>=<folder>.

Your part: lora_config() and train().
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAIN = ROOT / "data" / "train.jsonl"
BASE_MODEL = "Qwen/Qwen3-8B"
# A tiny Qwen3 model that the TRL team keeps for tests (about 20 MB), at a fixed revision.
SMOKE_MODEL = "trl-internal-testing/tiny-Qwen3ForCausalLM"
SMOKE_REVISION = "25bb9b8963688237e94750f6f3e48f1947d3c7a3"
SMOKE_EXAMPLES = 16
SMOKE_STEPS = 3


def load_examples(path: Path, limit: int | None = None):
    """The examples of data/train.jsonl as a dataset of the `datasets` library."""
    from datasets import load_dataset

    dataset = load_dataset("json", data_files=str(path), split="train")
    return dataset.select(range(min(limit, len(dataset)))) if limit else dataset


def training_config(output: Path, smoke: bool):
    """The settings of the trainer. The smoke mode runs a few steps on the CPU."""
    from trl import SFTConfig

    if smoke:
        return SFTConfig(output_dir=str(output), max_steps=SMOKE_STEPS, per_device_train_batch_size=2,
                         learning_rate=2e-4, logging_steps=1, save_strategy="no", report_to="none",
                         use_cpu=True, bf16=False, max_length=512, model_init_kwargs={"revision": SMOKE_REVISION})
    return SFTConfig(output_dir=str(output), num_train_epochs=2, per_device_train_batch_size=4,
                     gradient_accumulation_steps=4, learning_rate=2e-4, logging_steps=10, save_strategy="no",
                     report_to="none", bf16=True, max_length=1024)


def lora_config():
    """The LoRA settings: a peft.LoraConfig.

    Choose the rank (r), lora_alpha, lora_dropout and the target modules, for a causal language
    model (task_type). vLLM serves an adapter up to rank 16 by default (--max-lora-rank). The
    smoke model has the same module names as Qwen3-8B.
    """
    from peft import LoraConfig

    return LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )


def train(model: str, dataset, output: Path, smoke: bool) -> None:
    """Train the adapter with trl.SFTTrainer, and save it to `output`.

    Give the trainer the name of the model, the dataset, the LoRA settings of lora_config() and the
    settings of training_config(). With LoRA settings, the trainer trains and saves only the adapter
    (trainer.save_model).
    """
    from trl import SFTTrainer

    trainer = SFTTrainer(model=model, train_dataset=dataset, peft_config=lora_config(),
                         args=training_config(output, smoke))
    trainer.train()
    trainer.save_model(str(output))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--smoke", action="store_true", help="Train the tiny model for a few steps on the CPU.")
    parser.add_argument("--data", type=Path, default=TRAIN)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.smoke:
        output = args.output or ROOT / "train" / "smoke-adapter"
        train(SMOKE_MODEL, load_examples(args.data, SMOKE_EXAMPLES), output, smoke=True)
    else:
        output = args.output or Path("/workspace/adapter")
        train(BASE_MODEL, load_examples(args.data), output, smoke=False)
    saved = sorted(path.name for path in output.iterdir()) if output.exists() else []
    print(f"adapter in {output}: {saved}")


if __name__ == "__main__":
    main()
