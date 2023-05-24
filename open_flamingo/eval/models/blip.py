import argparse
from typing import List

from PIL import Image
import torch

from transformers import Blip2Processor, Blip2ForConditionalGeneration
from open_flamingo.eval.eval_model import BaseEvalModel

class EvalModel(BaseEvalModel):
    """BLIP-2 model evaluation.

    Attributes:
      model (nn.Module): Underlying Torch model.
      tokenizer (transformers.PreTrainedTokenizer): Tokenizer for model.
      device: Index of GPU to use, or the string "CPU"
    """

    def __init__(self, args: List[str]):
        parser = argparse.ArgumentParser()
        parser.add_argument("--lm_path", type=str, default="Salesforce/blip2-flan-t5-xl")
        parser.add_argument("--processor_path", type=str, default="Salesforce/blip2-flan-t5-xl")
        parser.add_argument("--device", type=int, default=0)
        args = parser.parse_args(args)

        # load model
        self.device = args.device if args.device >= 0 else "cpu"
        self.processor = Blip2Processor.from_pretrained(args.processor_path)
        self.model = Blip2ForConditionalGeneration.from_pretrained(
            args.lm_path
        )
        self.model.to(self.device)

    def _prepare_images(self, batch: List[List[torch.Tensor]]) -> torch.Tensor:
        """Preprocess images and stack them.

        Args:
            batch: A list of lists of images.

        Returns:
            A Tensor of shape
            (batch_size, channels, height, width).
        """
        batch_images = None
        assert all(
            len(example) == 1 for example in batch
        ), "BLIP-2 only supports one image per example"
        
        for example in batch:
            assert len(example) == 1, "BLIP-2 only supports one image per example"
            batch_images = torch.cat(
                [batch_images, self.processor.image_processor(example, return_tensors="pt")["pixel_values"]]
                if batch_images is not None
                else [self.processor.image_processor(example, return_tensors="pt")["pixel_values"]],
                dim=0,
            )
        return batch_images

    def get_outputs(
        self,
        batch_text: List[str],
        batch_images: List[List[Image.Image]],
        max_generation_length: int,
        num_beams: int,
        length_penalty: float,
    ) -> List[str]:
        self.model.eval()

        self.processor.tokenizer.padding_side = "left"
        encodings = self.processor.tokenizer(
            batch_text,
            padding="longest",
            truncation=True,
            return_tensors="pt",
            max_length=2000,
        )
        input_ids = encodings["input_ids"]
        attention_mask = encodings["attention_mask"]

        with torch.inference_mode():
            outputs = self.model.generate(
                self._prepare_images(batch_images).to(self.device),
                input_ids.to(self.device),
                attention_mask=attention_mask.to(self.device),
                max_new_tokens=max_generation_length,
                num_beams=num_beams,
                length_penalty=length_penalty,
            )

        return self.processor.tokenizer.batch_decode(outputs, skip_special_tokens=True)

    def vqa_prompt(self, question, answer=None) -> str:
        return f"Question:{question} Short answer:{answer if answer is not None else ''}"

    def caption_prompt(self, caption=None) -> str:
        return f"A photo of {caption if caption is not None else ''}"

    def classification_prompt(self, class_str=None) -> str:
        raise NotImplementedError