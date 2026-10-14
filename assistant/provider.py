"""
LLM Provider abstraction and Tool Calling loop for VIKMO DealerDesk Assistant.
Supports Google Gemini, Groq, OpenAI, and Anthropic with automatic detection.
Provides mockable interface for automated testing.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from dealerdesk.exceptions import ServiceUnavailableException
from assistant.tools import (
    TOOLS_SCHEMA_OPENAI,
    check_stock,
    create_draft_order,
    search_parts,
)

logger = logging.getLogger(__name__)


def get_active_provider_info() -> Tuple[str, str]:
    """
    Detect configured LLM provider from environment variables.
    Returns (provider_name, api_key).
    Supported variables per API_CONTRACT.md:
    - GEMINI_API_KEY
    - GROQ_API_KEY
    - OPENAI_API_KEY
    - ANTHROPIC_API_KEY
    """
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini", os.environ["GEMINI_API_KEY"].strip().strip("\"'")
    if os.environ.get("GROQ_API_KEY"):
        return "groq", os.environ["GROQ_API_KEY"].strip().strip("\"'")
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"].strip().strip("\"'")
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"].strip().strip("\"'")
    return "none", ""


def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    authorized_dealer_id: int,
    actions_accumulator: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Execute a validated tool by exact contract name.
    """
    if tool_name == "search_parts":
        query = args.get("query", "")
        vehicle = args.get("vehicle")
        return search_parts(query=query, vehicle=vehicle)

    elif tool_name == "check_stock":
        sku = args.get("sku", "")
        return check_stock(sku=sku)

    elif tool_name == "create_draft_order":
        dealer_id = args.get("dealer_id", authorized_dealer_id)
        items = args.get("items", [])
        return create_draft_order(
            dealer_id=dealer_id,
            items=items,
            authorized_dealer_id=authorized_dealer_id,
            actions_accumulator=actions_accumulator,
        )

    return {"error": f"Unknown tool: {tool_name}"}


class AssistantLLMClient:
    """
    Manages LLM communication and multi-turn tool calling execution.
    """

    def __init__(self):
        self.mock_handler = None  # Settable for unit tests

    def set_mock_handler(self, handler):
        """Set a callable handler for testing: handler(messages, tools) -> (reply, tool_calls, actions)"""
        self.mock_handler = handler

    def run_turn(
        self,
        system_prompt: str,
        history: List[Dict[str, Any]],
        user_message: str,
        authorized_dealer_id: int,
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Runs one assistant conversation turn.
        Returns:
            (reply, executed_tool_calls, actions, new_messages_to_record)
        """
        if self.mock_handler:
            return self.mock_handler(
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                authorized_dealer_id=authorized_dealer_id,
            )

        provider, api_key = get_active_provider_info()
        if provider == "none" or not api_key:
            raise ServiceUnavailableException(
                "No LLM provider key configured. Please set GEMINI_API_KEY, GROQ_API_KEY, "
                "OPENAI_API_KEY, or ANTHROPIC_API_KEY in the environment."
            )

        if provider == "groq":
            return self._run_openai_compatible_turn(
                base_url="https://api.groq.com/openai/v1",
                api_key=api_key,
                model="llama-3.3-70b-versatile",
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                authorized_dealer_id=authorized_dealer_id,
            )

        elif provider == "openai":
            return self._run_openai_compatible_turn(
                base_url=None,
                api_key=api_key,
                model="gpt-4o-mini",
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                authorized_dealer_id=authorized_dealer_id,
            )

        elif provider == "gemini":
            return self._run_gemini_turn(
                api_key=api_key,
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                authorized_dealer_id=authorized_dealer_id,
            )

        elif provider == "anthropic":
            return self._run_anthropic_turn(
                api_key=api_key,
                system_prompt=system_prompt,
                history=history,
                user_message=user_message,
                authorized_dealer_id=authorized_dealer_id,
            )

        raise ServiceUnavailableException(f"Unsupported LLM provider: {provider}")

    def _run_openai_compatible_turn(
        self,
        base_url: Optional[str],
        api_key: str,
        model: str,
        system_prompt: str,
        history: List[Dict[str, Any]],
        user_message: str,
        authorized_dealer_id: int,
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=50.0)
        except Exception as e:
            raise ServiceUnavailableException(f"Failed to initialize LLM client: {str(e)}")

        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_message})

        executed_tool_calls: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []
        new_recorded_messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOLS_SCHEMA_OPENAI,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=1000,
                )
            except Exception as e:
                logger.error(f"LLM API call failed: {e}")
                raise ServiceUnavailableException(f"LLM provider error: {str(e)}")

            choice = response.choices[0]
            message = choice.message

            # If model didn't call any tools, it's the final answer
            if not message.tool_calls:
                final_reply = message.content or ""
                new_recorded_messages.append({"role": "assistant", "content": final_reply})
                return final_reply, executed_tool_calls, actions, new_recorded_messages

            # Append the assistant message with tool calls
            tool_calls_data = []
            for tc in message.tool_calls:
                tool_calls_data.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
            messages.append({"role": "assistant", "tool_calls": tool_calls_data})
            new_recorded_messages.append({"role": "assistant", "tool_calls": tool_calls_data})

            # Execute each tool call
            for tc in message.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}

                executed_tool_calls.append({"name": fn_name, "arguments": args})

                result = execute_tool(
                    tool_name=fn_name,
                    args=args,
                    authorized_dealer_id=authorized_dealer_id,
                    actions_accumulator=actions,
                )

                tool_result_content = json.dumps(result, default=str)
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": tool_result_content,
                }
                messages.append(tool_msg)
                new_recorded_messages.append(tool_msg)

        # Fallback if loop exceeded max iterations
        return (
            "I processed your request using the parts database.",
            executed_tool_calls,
            actions,
            new_recorded_messages,
        )

    def _run_gemini_turn(
        self,
        api_key: str,
        system_prompt: str,
        history: List[Dict[str, Any]],
        user_message: str,
        authorized_dealer_id: int,
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Gemini supports the OpenAI-compatible endpoint:
        https://generativelanguage.googleapis.com/v1beta/openai/
        This allows unified, battle-tested tool calling syntax.
        """
        return self._run_openai_compatible_turn(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key.strip("\"'"),
            model="gemini-2.5-flash",
            system_prompt=system_prompt,
            history=history,
            user_message=user_message,
            authorized_dealer_id=authorized_dealer_id,
        )

    def _run_anthropic_turn(
        self,
        api_key: str,
        system_prompt: str,
        history: List[Dict[str, Any]],
        user_message: str,
        authorized_dealer_id: int,
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Anthropic Messages API fallback with tools.
        """
        import requests

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Convert tools to Anthropic tool schema
        anthropic_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in TOOLS_SCHEMA_OPENAI
        ]

        messages = []
        for msg in history:
            role = "user" if msg.get("role") == "user" else "assistant"
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        executed_tool_calls: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []
        new_recorded_messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            payload = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 1000,
                "system": system_prompt,
                "messages": messages,
                "tools": anthropic_tools,
            }
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=50.0,
            )
            if res.status_code != 200:
                raise ServiceUnavailableException(f"Anthropic API error: {res.text}")

            data = res.json()
            tool_calls_blocks = [b for b in data.get("content", []) if b.get("type") == "tool_use"]
            text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]

            if not tool_calls_blocks:
                final_reply = "".join(text_blocks)
                new_recorded_messages.append({"role": "assistant", "content": final_reply})
                return final_reply, executed_tool_calls, actions, new_recorded_messages

            # Execute tool use blocks
            messages.append({"role": "assistant", "content": data.get("content")})
            tool_response_content = []

            for tb in tool_calls_blocks:
                fn_name = tb.get("name")
                args = tb.get("input", {})
                executed_tool_calls.append({"name": fn_name, "arguments": args})

                result = execute_tool(
                    tool_name=fn_name,
                    args=args,
                    authorized_dealer_id=authorized_dealer_id,
                    actions_accumulator=actions,
                )
                tool_response_content.append({
                    "type": "tool_result",
                    "tool_use_id": tb.get("id"),
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_response_content})

        return (
            "I processed your request using the parts database.",
            executed_tool_calls,
            actions,
            new_recorded_messages,
        )


# Global singleton client
assistant_client = AssistantLLMClient()
