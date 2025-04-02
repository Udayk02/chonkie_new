"""Chonkie: Recursive Chunker
Splits text into smaller chunks recursively. Express chunking logic through RecursiveLevel objects.
"""

from __future__ import annotations
from bisect import bisect_left
from functools import lru_cache
from itertools import accumulate
from typing import Any, Callable, Literal, Sequence
from chonkie.chunkers.base import BaseChunker
from chonkie.types.recurisve import (
    RecursiveChunk,
    RecursiveLevel,
    RecursiveRules,
)


class RecursiveChunker(BaseChunker):
    """Chunker that recursively splits text into smaller chunks, based on the provided RecursiveRules.


    Attributes:
        tokenizer_or_token_counter (str | Callable | Any): Tokenizer or token counter to use
        recursive_rules (list[RecursiveLevel]): List of RecursiveLevel objects defining chunking rules at a level.
        chunk_size (int): Maximum size of each chunk.
        min_characters_per_chunk (int): Minimum number of characters per chunk.
        return_type (str): Type of return value, either 'chunks' or 'texts'.
    """

    _CHARS_PER_TOKEN = 6

    def __init__(
        self,
        tokenizer_or_token_counter: str | Callable | Any = "gpt2",
        recursive_rules: RecursiveRules = RecursiveRules(),
        chunk_size: int = 512,
        min_characters_per_chunk: int = 24,
        return_type: Literal["texts", "chunks"] = "chunks",
    ) -> None:
        """Create a RecursiveChunker object.

        Args:
            tokenizer_or_token_counter (str | Callable | Any): Tokenizer or token counter to use
            recursive_rules (list[RecursiveLevel]): List of RecursiveLevel objects defining chunking rules at a level.
            chunk_size (int): Maximum size of each chunk.
            min_characters_per_chunk (int): Minimum number of characters per chunk.
            return_type (str): Type of return value, either 'chunks' or 'texts'.

        Raises:
            ValueError: If chunk_size <=0
            ValueError: If min_characters_per_chunk < 1
            ValueError: If return_type is not 'chunks' or 'texts'.
            ValueError: If recursive_rules is not a RecursiveRules object.

        """
        super().__init__(tokenizer_or_token_counter=tokenizer_or_token_counter)

        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if min_characters_per_chunk <= 0:
            raise ValueError("min_characters_per_chunk must be greater than 0")
        if return_type not in ["chunks", "texts"]:
            raise ValueError(
                f"return_type {return_type} is invalid. Must be 'chunks' or 'texts'."
            )
        if not isinstance(recursive_rules, RecursiveRules):
            raise ValueError("recursive_rules must be a RecursiveRules object.")

        self.chunk_size = chunk_size
        self.min_characters_per_chunk = min_characters_per_chunk
        self.return_type = return_type
        self.recursive_rules = recursive_rules

    def toStr(self) -> str:
        """Get a string representation of the recursive chunker."""
        return (
            f"RecursiveChunker(recursive_rules={self.recursive_rules}, chunk_size={self.chunk_size}, "
            f"min_characters_per_chunk={self.min_characters_per_chunk}, "
            f"return_type={self.return_type})"
        )

    def __repr__(self) -> str:
        """Get a string representation of the recursive chunker."""
        return self.toStr()

    def __str__(self) -> str:
        """Get a string representation of the recursive chunker."""
        return self.toStr()

    @lru_cache(maxsize=2048)
    def _estimate_token_count(self, text: str) -> int:
        estimate = max(1, len(text) // self._CHARS_PER_TOKEN)
        return (
            float("inf")
            if estimate > self.chunk_size
            else self.tokenizer.count_tokens(text)
        )

    def _split(
        self,
        text: str,
        recursive_level: RecursiveLevel,
        sep: str = "<=CHONKIE_INTERNAL_SEP=>",
    ) -> list[str]:
        """Split the text into chunks using the delimiters."""
        # At every delimiter, replace it with the sep
        if recursive_level.whitespace_delimiter:
            splits = text.split(" ")
        elif recursive_level.custom_delimiters:
            if recursive_level.include_delim == "prev":
                for delimiter in recursive_level.delimiters:
                    text = text.replace(delimiter, delimiter + sep)
            elif recursive_level.include_delim == "next":
                for delimiter in recursive_level.delimiters:
                    text = text.replace(delimiter, sep + delimiter)
            else:
                for delimiter in recursive_level.delimiters:
                    text = text.replace(delimiter, sep)

            splits = [split for split in text.split(sep) if split != ""]

            # Merge short splits
            current = ""
            merged = []
            for split in splits:
                if len(split) < self.min_characters_per_chunk:
                    current += split
                elif current:
                    current += split
                    merged.append(current)
                    current = ""
                else:
                    merged.append(split)

                if len(current) >= self.min_characters_per_chunk:
                    merged.append(current)
                    current = ""

            if current:
                merged.append(current)

            splits = merged
        else:
            # Encode, Split, and Decode
            encoded = self.tokenizer.encode(text)
            token_splits = [
                encoded[i : i + self.chunk_size]
                for i in range(0, len(encoded), self.chunk_size)
            ]
            splits = self.tokenizer.decode_batch(token_splits)

        # Some splits may not be meaningful yet.
        # This will be handled during chunk creation.
        return splits

    def _convert_to_chunk(
        self,
        text: str,
        token_count: int,
        level: int,
        full_text: str | None = None,
        last_chunk_end_index: int = 0,
    ) -> RecursiveChunk:
        """Form and return a RecursiveChunk object."""
        if full_text is None:
            full_text = text
        try:
            start_index = last_chunk_end_index + full_text[
                last_chunk_end_index:
            ].index(text)
            end_index = start_index + len(text)
        except Exception as e:
            print(
                f"Error finding start and end index for text '{text}' in full_text. Error: {e}"
                f"Setting start and end index to 0."
            )
            start_index = 0
            end_index = 0

        return RecursiveChunk(
            text=text,
            start_index=start_index,
            end_index=end_index,
            token_count=token_count,
            level=level,
        )

    def _merge_splits(
        self,
        splits: list[str],
        token_counts: list[int],
        combine_whitespace: bool = False,
    ) -> list[str]:
        """Merge short splits."""

        if not splits or not token_counts:
            return [], []

        # If the number of splits and token counts does not match, raise an error
        if len(splits) != len(token_counts):
            raise ValueError(
                f"Number of splits {len(splits)} does not match number of token counts {len(token_counts)}"
            )

        # If all splits are larger than the chunk size, return them
        if all(counts > self.chunk_size for counts in token_counts):
            return splits, token_counts

        # If the splits are too short, merge them
        merged = []
        if combine_whitespace:
            # +1 for the whitespace
            cumulative_token_counts = list(
                accumulate([0] + token_counts, lambda x, y: x + y + 1)
            )
        else:
            cumulative_token_counts = list(accumulate([0] + token_counts))
        current_index = 0
        combined_token_counts = []

        while current_index < len(splits):
            current_token_count = cumulative_token_counts[current_index]
            required_token_count = current_token_count + self.chunk_size

            # Find the index to merge at
            index = min(
                bisect_left(
                    cumulative_token_counts,
                    required_token_count,
                    lo=current_index,
                )
                - 1,
                len(splits),
            )

            # If current_index == index,
            # we need to move to the next index
            if index == current_index:
                index += 1

            # Merge splits
            if combine_whitespace:
                merged.append(" ".join(splits[current_index:index]))
            else:
                merged.append("".join(splits[current_index:index]))

            # Adjust token count
            combined_token_counts.append(
                cumulative_token_counts[min(index, len(splits))]
                - current_token_count
            )
            current_index = index

        return merged, combined_token_counts

    def _chunk_helper(
        self, text: str, level: int = 0, full_text: str | None = None
    ) -> Sequence[RecursiveChunk]:
        """Recursive helper for core chunking."""
        if not text:
            return []

        if level >= len(self.rules):
            if self.return_type == "texts":
                return [text]
            if self.return_type == "chunks":
                return [
                    self._convert_to_chunk(
                        text, self._get_token_count(text), level, full_text
                    )
                ]
            raise ValueError(
                f"Invalid return_type {self.return_type}. Must be 'chunks' or 'texts'."
            )

        if full_text is None:
            full_text = text

        curr_rule = self.recursive_rules[level]
        splits = self._split(text, curr_rule)
        token_counts = [self._estimate_token_count(split) for split in splits]

        # Merge splits
        # If no delimeters and no whitespace, we can just use the splits
        # If no delimeters and whitespace, we need to merge the splits
        # If delimeters and whitespace, we need to merge the splits
        if curr_rule.delimiters is None and not curr_rule.whitespace:
            merged, combined_token_counts = splits, token_counts

        elif curr_rule.delimiters is None and curr_rule.whitespace:
            merged, combined_token_counts = self._merge_splits(
                splits, token_counts, combine_whitespace=True
            )
        else:
            merged, combined_token_counts = self._merge_splits(
                splits, token_counts, combine_whitespace=False
            )

        # Chunk long merged splits
        chunks = []
        for split, token_count in zip(merged, combined_token_counts):
            if token_count > self.chunk_size:
                chunks.extend(self._chunk_helper(split, level + 1, full_text))
            else:
                if self.return_type == "chunks":
                    no_delim = (
                        curr_rule.delimiters is None
                        and not curr_rule.whitespace
                    )
                    # **Speedup**: Since there are no delimiters we can just join the "merged" result.
                    chunks.append(
                        self._convert_to_chunk(
                            split,
                            token_count,
                            level,
                            ("".join(merged) if no_delim else full_text),
                        )
                    )
                elif self.return_type == "texts":
                    chunks.append(split)
        return chunks

    def chunk(self, text: str) -> Sequence[RecursiveChunk]:
        return self._chunk_helper(text=text, level=0, full_text=text)
