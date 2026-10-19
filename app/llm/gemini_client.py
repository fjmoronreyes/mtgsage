"""Google Gemini adapter for generative responses and manual tool calling."""

import os
from time import perf_counter
from typing import Literal

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY
from app.logger import get_logger


logger = get_logger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash-lite"
ToolMode = Literal["AUTO", "ANY", "NONE"]


class GeminiClient:
    """Manage Gemini requests and the underlying HTTP client."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self.model = (
            model
            or os.getenv("MTGSAGE_GENERATIVE_MODEL")
            or DEFAULT_MODEL
        )
        self._owns_client = client is None

        if client is not None:
            self._client = client
        else:
            key = api_key or GEMINI_API_KEY
            if not key:
                raise ValueError(
                    "GEMINI_API_KEY is not configured. "
                    "Check your environment or .env file."
                )
            self._client = genai.Client(api_key=key)

        logger.info("Gemini client configured | model=%s", self.model)

    def __enter__(self) -> "GeminiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(
        self,
        contents: str | list[types.Content],
        *,
        tools: list[types.Tool] | None = None,
        system_instruction: str | None = None,
        tool_mode: ToolMode = "AUTO",
    ) -> types.GenerateContentResponse:
        """Generate a response with explicit function-calling policy.

        AUTO: model may answer or request a function.
        ANY: model must request a function (when tools are supplied).
        NONE: model may not request a function (final synthesis).
        """
        if tool_mode not in ("AUTO", "ANY", "NONE"):
            raise ValueError(f"Unsupported function calling mode: {tool_mode}")
        if tool_mode == "ANY" and not tools:
            raise ValueError("ANY function calling requires declared tools")
        if tool_mode == "NONE" and not tools:
            raise ValueError("NONE mode requires declared tools")

        started = perf_counter()
        response = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                tool_config=(
                    types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode=tool_mode
                        )
                    )
                    if tools is not None else None
                ),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )

        usage = response.usage_metadata
        logger.info(
            "Gemini response received | model=%s | mode=%s | "
            "duration=%.2fs | tool_calls=%d | "
            "input_tokens=%s | output_tokens=%s",
            self.model,
            tool_mode,
            perf_counter() - started,
            len(response.function_calls or []),
            usage.prompt_token_count if usage else None,
            usage.candidates_token_count if usage else None,
        )
        return response
