"""Huấn luyện QLoRA cho khâu phân tích, từ bộ train/dev do `build_training_set.py` dựng.

    D:/Novels/LLM_Train/.venv/Scripts/python.exe scripts/model_eval/train_lora.py --smoke 8
    D:/Novels/LLM_Train/.venv/Scripts/python.exe scripts/model_eval/train_lora.py --epochs 1

**Chạy bằng venv RIÊNG** `D:/Novels/LLM_Train/.venv` (torch 2.11+cu128, transformers 5.17, peft 0.21, trl 1.13,
bitsandbytes 0.50.2) - KHÔNG phải `runtime/.venv` của dây chuyền: nâng gói trong runtime là đổi hash chính sách
chất lượng, và cái đó chỉ được làm ở ranh giới.

Model nền: `Qwen/Qwen3-4B-Instruct-2507`. Cùng họ với model sản xuất (`qwen3:8b`) nên prompt không phải viết lại,
nhỏ đủ để QLoRA 4-bit vừa 8 GB VRAM, và bản `-Instruct-2507` KHÔNG có chế độ nghĩ - chế độ ấy chính là thứ làm
`qwen3.5:9b` trả về "0/5 IDs" trong lượt đo đêm 19-09.

Số đo để chọn tham số (tokenizer Qwen3, 20-09): mỗi mẫu trung vị **3.213** token, p99 4.069, tối đa **4.276**; riêng
câu trả lời trung vị 369, tối đa 784. Nên `--max-length 4352` giữ TRỌN mọi mẫu - cắt ngắn ở đây là cắt mất câu trả
lời, tức huấn luyện trên một đề bài không có đáp án. Một epoch = 1.727 mẫu = **5,29M token**.

`assistant_only_loss=True`: chỉ tính loss trên câu trả lời. Không có nó thì model học cả việc sinh lại đề bài -
mà đề bài là prompt sản xuất, thứ nó sẽ luôn được cho sẵn.

Bộ canh GPU: script TỪ CHỐI chạy khi có lượt sản xuất đang bay (dùng lại `_runs_in_flight` của `apply_all.py` chứ
không viết bộ canh thứ hai - docstring của hàm ấy ghi hai lần bộ canh tự viết đã sai). Máy chỉ có 8 GB VRAM:
huấn luyện chen vào giữa một lượt thu là ném cả lượt ấy vào OOM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASE = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_DATA = Path(r"D:/Novels/LLM_Train/data")
DEFAULT_OUT = Path(r"D:/Novels/LLM_Train/runs")
# Trên mọi mẫu đã đo, mẫu dài nhất là 4.276 token; để trần cao hơn nó một nhịp.
DEFAULT_MAX_LENGTH = 4352


def load_rows(path: Path, only: str) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if only != "both":
        rows = [row for row in rows if row.get("type") == only]
    return [{"messages": row["messages"]} for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=None, help="mặc định runs/<tên model>-<only>-r<r>")
    parser.add_argument("--only", choices=("both", "generator", "critic"), default="both")
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--r", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--accum", type=int, default=8, help="batch hiệu dụng = accum (batch mỗi bước luôn là 1)")
    parser.add_argument("--smoke", type=int, default=0, help="chỉ N mẫu và 3 bước - kiểm đường ống, không huấn luyện")
    parser.add_argument("--force", action="store_true", help="chạy dù có lượt sản xuất đang bay (sẽ tranh VRAM)")
    parser.add_argument("--optim", default="paged_adamw_8bit",
                        help="paged_adamw_8bit (mặc định) hay adamw_8bit - bản `paged` đẩy trạng thái qua PCIe khi "
                             "VRAM chật, và trên 8 GB đó có thể là nút cổ chai lớn nhất")
    args = parser.parse_args(argv)

    from scripts.pending_patches.apply_all import _runs_in_flight  # noqa: PLC0415  (dùng lại bộ canh đã đo)

    flying = _runs_in_flight()
    if flying and not args.force:
        for project, reason in flying:
            print(f"  đang bay: {project.name} ({reason})")
        raise SystemExit("từ chối: máy chỉ có 8 GB VRAM, huấn luyện lúc này là ném lượt sản xuất vào OOM")

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    train_rows = load_rows(args.data / "train.jsonl", args.only)
    dev_rows = load_rows(args.data / "dev.jsonl", args.only)
    if args.smoke:
        train_rows = train_rows[: args.smoke]
        dev_rows = dev_rows[: max(2, args.smoke // 4)]
    out = args.out or (DEFAULT_OUT / f"{args.base.split('/')[-1]}-{args.only}-r{args.r}")
    print(f"  model nền {args.base} | train {len(train_rows)} mẫu, dev {len(dev_rows)} | ra {out}")

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    config = SFTConfig(
        output_dir=str(out),
        num_train_epochs=args.epochs if not args.smoke else 1.0,
        max_steps=3 if args.smoke else -1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=args.accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        # TRL 1.13 ở venv này KHÔNG có `warmup_ratio` (chỉ `warmup_steps`) - đã thử và nó ném TypeError.
        warmup_steps=max(5, int(0.03 * len(train_rows) / max(1, args.accum))),
        logging_steps=5,
        save_steps=200,
        save_total_limit=2,
        eval_strategy="steps" if dev_rows else "no",
        eval_steps=100,
        per_device_eval_batch_size=1,
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim=args.optim,
        max_length=args.max_length,
        packing=False,          # mỗi mẫu là một lượt hỏi trọn vẹn; ghép chúng lại là trộn hai đề bài
        assistant_only_loss=True,
        model_init_kwargs={"quantization_config": quantization, "dtype": torch.bfloat16},
        report_to=[],
        seed=1234,
    )
    trainer = SFTTrainer(
        model=args.base,
        args=config,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(dev_rows) if dev_rows else None,
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=args.r,
            lora_alpha=args.alpha,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        ),
    )
    trainer.train()
    trainer.save_model(str(out))
    tokenizer.save_pretrained(str(out))
    print(f"  đã lưu adapter vào {out}")
    print("  bước tiếp: gộp adapter rồi `ollama create` để chấm bằng scripts/model_eval/eval_models.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
