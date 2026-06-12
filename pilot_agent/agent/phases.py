from __future__ import annotations

from dataclasses import dataclass

from pilot_agent.agent import prompts


@dataclass(frozen=True)
class Phase:
    name: str
    prompt: str
    tools: list[str]
    next: str | None


PIPELINE = ["discovery", "planning", "coding", "deploy", "marketing"]

PHASES: dict[str, Phase] = {
    "discovery": Phase(
        name="discovery",
        prompt=prompts.discovery_prompt(),
        tools=["ask_user", "web_search", "complete_phase"],
        next="planning",
    ),
    "planning": Phase(
        name="planning",
        prompt=prompts.planning_prompt(),
        tools=[
            "ask_user",
            "read_file",
            "write_file",
            "list_files",
            "web_search",
            "web_fetch",
            "load_skill",
            "complete_phase",
        ],
        next="coding",
    ),
    "coding": Phase(
        name="coding",
        prompt=prompts.coding_prompt(),
        tools=[
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "bash",
            "run_and_check",
            "web_search",
            "web_fetch",
            "load_skill",
            "ask_user",
            "complete_phase",
        ],
        next="deploy",
    ),
    "deploy": Phase(
        name="deploy",
        prompt=prompts.deploy_prompt(),
        tools=[
            "bash",
            "run_and_check",
            "read_file",
            "edit_file",
            "load_skill",
            "save_skill",
            "ask_user",
            "complete_phase",
        ],
        next="marketing",
    ),
    "marketing": Phase(
        name="marketing",
        prompt=prompts.marketing_prompt(),
        tools=["read_file", "write_file", "load_skill", "ask_user", "complete_phase"],
        next=None,
    ),
}
