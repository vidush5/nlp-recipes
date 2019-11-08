# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import numpy as np
import torch
from torch.utils.data import TensorDataset

from transformers.modeling_bert import (
    BERT_PRETRAINED_MODEL_ARCHIVE_MAP,
    BertForSequenceClassification,
)
from transformers.modeling_distilbert import (
    DISTILBERT_PRETRAINED_MODEL_ARCHIVE_MAP,
    DistilBertForSequenceClassification,
)
from transformers.modeling_roberta import (
    ROBERTA_PRETRAINED_MODEL_ARCHIVE_MAP,
    RobertaForSequenceClassification,
)
from transformers.modeling_xlnet import (
    XLNET_PRETRAINED_MODEL_ARCHIVE_MAP,
    XLNetForSequenceClassification,
)

from utils_nlp.common.pytorch_utils import get_device
from utils_nlp.models.transformers.common import MAX_SEQ_LEN, TOKENIZER_CLASS, Transformer


MODEL_CLASS = {}
MODEL_CLASS.update({k: BertForSequenceClassification for k in BERT_PRETRAINED_MODEL_ARCHIVE_MAP})
MODEL_CLASS.update(
    {k: RobertaForSequenceClassification for k in ROBERTA_PRETRAINED_MODEL_ARCHIVE_MAP}
)
MODEL_CLASS.update({k: XLNetForSequenceClassification for k in XLNET_PRETRAINED_MODEL_ARCHIVE_MAP})
MODEL_CLASS.update(
    {k: DistilBertForSequenceClassification for k in DISTILBERT_PRETRAINED_MODEL_ARCHIVE_MAP}
)


class Processor:
    def __init__(self, model_name="bert-base-cased", to_lower=False, cache_dir="."):
        self.tokenizer = TOKENIZER_CLASS[model_name].from_pretrained(
            model_name, do_lower_case=to_lower, cache_dir=cache_dir, output_loading_info=False
        )

    @staticmethod
    def get_inputs(batch, model_name, train_mode=True):
        if model_name.split("-")[0] in ["bert", "xlnet", "roberta", "distilbert"]:
            if train_mode:
                return {"input_ids": batch[0], "attention_mask": batch[1], "labels": batch[2]}
            else:
                return {"input_ids": batch[0], "attention_mask": batch[1]}
        else:
            raise ValueError("Model not supported: {}".format(model_name))

    def preprocess(self, text, labels=None, max_len=MAX_SEQ_LEN):
        """preprocess data or batches"""
        if max_len > MAX_SEQ_LEN:
            print("setting max_len to max allowed sequence length: {}".format(MAX_SEQ_LEN))
            max_len = MAX_SEQ_LEN

        tokens = [self.tokenizer.tokenize(x) for x in text]

        # truncate and add CLS & SEP markers
        tokens = [
            [self.tokenizer.cls_token] + x[0 : max_len - 2] + [self.tokenizer.sep_token]
            for x in tokens
        ]
        # get input ids
        input_ids = [self.tokenizer.convert_tokens_to_ids(x) for x in tokens]
        # pad sequence
        input_ids = [x + [0] * (max_len - len(x)) for x in input_ids]
        # create input mask
        input_mask = [[min(1, x) for x in y] for y in input_ids]
        # create segment ids
        # segment_ids = None
        if labels is None:
            td = TensorDataset(
                torch.tensor(input_ids, dtype=torch.long),
                torch.tensor(input_mask, dtype=torch.long),
            )
        else:
            td = TensorDataset(
                torch.tensor(input_ids, dtype=torch.long),
                torch.tensor(input_mask, dtype=torch.long),
                torch.tensor(labels, dtype=torch.long),
            )
        return td


class SequenceClassifier(Transformer):
    def __init__(self, model_name="bert-base-cased", num_labels=2, cache_dir="."):
        super().__init__(
            model_class=MODEL_CLASS,
            model_name=model_name,
            num_labels=num_labels,
            cache_dir=cache_dir,
        )

    @staticmethod
    def list_supported_models():
        return list(MODEL_CLASS)

    def fit(
        self,
        train_dataset,
        num_epochs=1,
        batch_size=32,
        num_gpus=None,
        local_rank=-1,
        weight_decay=0.0,
        learning_rate=5e-5,
        adam_epsilon=1e-8,
        warmup_steps=0,
        verbose=True,
        seed=None,
    ):
        """
        Fine-tunes a pre-trained sequence classification model.
        """

        device, num_gpus = get_device(num_gpus=num_gpus, local_rank=local_rank)
        self.model.to(device)
        super().fine_tune(
            train_dataset=train_dataset,
            get_inputs=Processor.get_inputs,
            device=device,
            per_gpu_train_batch_size=batch_size,
            n_gpu=num_gpus,
            num_train_epochs=num_epochs,
            weight_decay=weight_decay,
            learning_rate=learning_rate,
            adam_epsilon=adam_epsilon,
            warmup_steps=warmup_steps,
            verbose=verbose,
            seed=seed,
        )

    def predict(self, eval_dataset, batch_size=16, num_gpus=1, verbose=True):
        device, num_gpus = get_device(num_gpus=num_gpus, local_rank=-1)
        preds = list(
            super().predict(
                eval_dataset=eval_dataset,
                get_inputs=Processor.get_inputs,
                device=device,
                per_gpu_eval_batch_size=batch_size,
                n_gpu=num_gpus,
                verbose=verbose,
            )
        )
        preds = np.concatenate(preds)
        # todo generator & probs
        return np.argmax(preds, axis=1)
