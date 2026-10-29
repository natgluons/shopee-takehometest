# Model training and fine-tuning

## Start from the objective

Fine-tuning is not the default answer. Use prompt engineering, retrieval, and constrained tools
first when the problem is missing knowledge or missing guardrails. Fine-tune when you need a
consistent behavior, a specific output format, a domain style, or better performance on a narrow
task that prompting cannot reach. Be explicit about the target metric before collecting data.

## From raw data to a training set

### 1. Inventory and legality

- Record the source, license, collection date, and consent or contractual basis.
- Remove secrets, personal data, and content you are not allowed to train on.
- Keep a data card that describes provenance and known gaps.

### 2. Cleaning

- Fix encoding, normalize whitespace, and drop empty or corrupted records.
- Strip navigation, boilerplate, repeated headers, and template noise.
- Normalize dates, numbers, and units if the task depends on them.
- Deduplicate exact matches and near duplicates using hashing or shingling. Duplicates inflate
  evaluation scores and cause memorization.

### 3. Splitting

Split before training into train, validation, and test. Split by entity when records are correlated.
For example, split by customer or document, not by row, so the same receipt does not appear in both
train and test. Record the split seed and manifest.

### 4. Formatting

- Choose a chat template and apply it consistently to every example.
- For instruction tuning, store `system`, `user`, and `assistant` turns.
- For classification or extraction, store the exact target schema and a canonical serialization.
- Mask prompt tokens so the loss is computed on the completion only.
- Validate sequence lengths and decide on truncation or packing.

### 5. Quality over quantity

A few thousand carefully reviewed examples usually beat millions of noisy ones for instruction
tuning. Use heuristics plus human review. Measure label agreement and keep an error analysis log.
Add hard negatives and edge cases such as empty results, ambiguous dates, and mixed currencies.

## Choosing the training method

| Method | Data need | Compute | When to use |
| --- | --- | --- | --- |
| Prompting and tools | None | None | Missing knowledge or a single task |
| Retrieval augmented generation | A corpus | Low | Changing knowledge, citations needed |
| LoRA or QLoRA | 1k to 100k examples | Moderate | Style, format, and narrow task behavior |
| Full supervised fine tuning | 10k+ examples | High | Strong behavior change with stable data |
| Continued pretraining | Billions of tokens | Very high | New domain language and knowledge |
| Preference optimization | Paired preferences | Moderate to high | Aligning tone and helpfulness |

## Training recipe

1. Pin the base model revision and tokenizer.
2. Start with a low learning rate, for example 1e-5 to 2e-4 for full tuning and higher for LoRA
   depending on the rank.
3. Use a warmup of 1 to 5 percent and a cosine or linear decay schedule.
4. Choose batch size by memory. Use gradient accumulation to reach an effective batch size.
5. Enable mixed precision and gradient checkpointing if memory is tight.
6. Evaluate on the validation set at fixed intervals. Save the best checkpoint.
7. Monitor loss, gradient norm, throughput, and GPU memory.
8. Stop early when validation performance plateaus.

## Evaluation

- Use a held-out test set that was never used for any decision.
- Report task metrics such as exact match, F1, schema validity, and numeric accuracy.
- Compare against the base model and against a strong prompt-only baseline.
- Run a human review on a stratified sample.
- Test paraphrases and out-of-distribution inputs.
- Check safety, refusal behavior, and instruction following.
- Keep an evaluation dataset and harness in the repository so results are reproducible.

## Serving and operations

- Merge LoRA adapters into the base model or serve adapters dynamically.
- Quantize for cost and latency after measuring quality impact.
- Version the model, tokenizer, prompt template, and evaluation results together.
- Keep a rollback path to the previous model.
- Monitor input drift, output schema failure rate, and user feedback.
- Retrain on a schedule or when the evaluation suite shows regressions.

## Cost and risk notes

- Fine-tuning does not reliably add fresh facts. Retrieval is better for changing knowledge.
- Small datasets can cause overfitting and reduced general ability.
- Data licensing and privacy are the most common blockers.
- Training infrastructure is the easy part. Data quality and evaluation are the hard part.
