from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import date, time
from typing import Any, Generator

from dotenv import load_dotenv

load_dotenv()

import anthropic

from pawpal_system import Frequency, Owner, Pet, Scheduler, Task, TaskType

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s [%(levelname)s] [run=%(run_id)s] %(name)s: %(message)s"


class _CorrelationFilter(logging.Filter):
    """Injects a run_id into every LogRecord so all events in one agent
    session share a traceable ID in the log output."""

    def __init__(self) -> None:
        super().__init__()
        self._run_id = "no-run"

    def set_run_id(self, run_id: str) -> None:
        self._run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self._run_id
        return True


_correlation_filter = _CorrelationFilter()


def setup_logging() -> logging.Logger:
    """Configure the 'pawpal' logger with file and console handlers.
    Safe to call multiple times — guards against duplicate handlers."""
    logger = logging.getLogger("pawpal")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(_LOG_FORMAT)

    file_handler = logging.FileHandler("pawpal.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_correlation_filter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(_correlation_filter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = setup_logging()


@contextmanager
def agent_run(label: str) -> Generator[str, None, None]:
    """Stamp a fresh correlation ID for one agent session.

    Usage::
        with agent_run("care_plan") as run_id:
            ...
    """
    run_id = f"{label}-{uuid.uuid4().hex[:8]}"
    _correlation_filter.set_run_id(run_id)
    logger.info("Agent run started: %s", label)
    try:
        yield run_id
    except Exception:
        logger.exception("Agent run failed: %s", label)
        raise
    finally:
        logger.info("Agent run ended: %s", label)
        _correlation_filter.set_run_id("no-run")


# ---------------------------------------------------------------------------
# System prompt constants
# ---------------------------------------------------------------------------

CARE_PLAN_SYSTEM_INSTRUCTIONS = """\
You are a helpful pet care planning assistant integrated into PawPal+.
Your role is to help pet owners plan their day and manage their pet care schedule.

When asked to plan a day:
1. Call get_conflicts() first — always mention any conflicts found.
2. Call get_pending_tasks() to see what needs doing.
3. Use generate_daily_plan() with the owner's available hours (ask if unspecified).
4. Present the plan grouped by pet, with clear priority reasoning.

When the user asks to add, book, or schedule a task or appointment:
- Use schedule_task() to create it immediately. The task will appear in the schedule right away.
- Confirm what was created and tell the user to check the Schedule tab to see it.
- For vet appointments and one-off tasks, use frequency "As Needed" and include a due_date.

Guidelines:
- Acknowledge the owner by name.
- Flag conflicts constructively — suggest moving tasks rather than just warning.
- If tasks were skipped due to time limits, explain why.
- Keep responses warm and concise."""

HEALTH_ADVISOR_SYSTEM_INSTRUCTIONS = """\
You are a knowledgeable pet health advisor integrated into PawPal+.
Your role is to help owners stay on top of their pets' health.

When answering health questions:
1. Use your tools to gather relevant data before answering.
2. Check for overdue medications and vet appointments — flag these urgently.
3. Analyze completed task history to identify patterns.
4. Provide actionable, breed- and age-appropriate health tips.
5. Use add_health_note() to record significant observations.

When the user asks to schedule a medication reminder or vet appointment:
- Use schedule_task() to create it immediately.
- Confirm what was scheduled and tell the user to check the Schedule tab.
- For one-off appointments, use frequency "As Needed" and include a due_date.
- For ongoing medications, use frequency "Daily" or "Weekly" as appropriate.

Guidelines:
- Be warm, reassuring, and practical.
- Never diagnose — recommend vet consultations for medical concerns.
- Remember prior conversation turns and build on them.
- Keep responses focused and medically responsible."""

# ---------------------------------------------------------------------------
# Shared tool definitions
# ---------------------------------------------------------------------------

_SCHEDULE_TASK_TOOL: dict[str, Any] = {
    "name": "schedule_task",
    "description": (
        "Creates a new task and adds it directly to a pet's schedule. "
        "Use this when the user asks to add, book, or schedule anything — "
        "a vet appointment, medication, walk, grooming session, etc. "
        "The task appears in the Schedule tab immediately after creation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pet_name": {
                "type": "string",
                "description": "Name of the pet to assign this task to.",
            },
            "task_type": {
                "type": "string",
                "enum": ["Walk", "Feeding", "Medicine", "Grooming", "Vet Appointment"],
                "description": "Category of the task.",
            },
            "description": {
                "type": "string",
                "description": "Human-readable task name, e.g. 'Annual checkup' or 'Flea treatment'.",
            },
            "duration": {
                "type": "integer",
                "description": "Estimated duration in minutes.",
                "minimum": 1,
            },
            "priority": {
                "type": "integer",
                "description": "Priority from 1 (low) to 5 (high).",
                "minimum": 1,
                "maximum": 5,
            },
            "frequency": {
                "type": "string",
                "enum": ["Daily", "Weekly", "Monthly", "As Needed"],
                "description": (
                    "Recurrence pattern. Use 'As Needed' for one-off appointments. "
                    "Use 'Daily' for ongoing medications."
                ),
            },
            "preferred_hour": {
                "type": "integer",
                "description": "Preferred start hour (0–23). Omit if flexible.",
                "minimum": 0,
                "maximum": 23,
            },
            "due_date": {
                "type": "string",
                "description": (
                    "ISO date string (YYYY-MM-DD) for when this task is due. "
                    "Required for 'As Needed' tasks; useful for 'Weekly' tasks."
                ),
            },
        },
        "required": ["pet_name", "task_type", "description", "duration", "priority", "frequency"],
    },
}

# ---------------------------------------------------------------------------
# Care Plan Agent tool definitions
# ---------------------------------------------------------------------------

CARE_PLAN_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_pending_tasks",
        "description": (
            "Returns all incomplete tasks for a specific pet or all pets. "
            "Call this before generating a plan to understand what needs to be done."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Filter to this pet's name. Omit for all pets.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_conflicts",
        "description": (
            "Detects scheduling conflicts where two tasks overlap in time. "
            "Always call this when building a plan — mention any conflicts to the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "generate_daily_plan",
        "description": (
            "Generates a priority-sorted daily care plan that fits within the "
            "owner's available hours, respecting existing time commitments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "available_hours": {
                    "type": "integer",
                    "description": "How many hours the owner has free today (1–24).",
                    "minimum": 1,
                    "maximum": 24,
                },
            },
            "required": ["available_hours"],
        },
    },
    {
        "name": "get_pet_info",
        "description": "Returns breed, age, and task summary for one or all pets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Specific pet name, or omit for all pets.",
                },
            },
            "required": [],
        },
    },
    _SCHEDULE_TASK_TOOL,
]

# ---------------------------------------------------------------------------
# Health Advisor Agent tool definitions
# ---------------------------------------------------------------------------

HEALTH_ADVISOR_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_pet_health_history",
        "description": (
            "Returns the list of health notes recorded for a pet, "
            "plus all completed tasks (serving as activity history)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "The name of the pet to look up.",
                },
            },
            "required": ["pet_name"],
        },
    },
    {
        "name": "get_medication_tasks",
        "description": (
            "Returns all MEDICINE-type tasks (complete and incomplete) "
            "for one or all pets. Flags overdue medications."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Filter to a specific pet, or omit for all.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_vet_appointments",
        "description": (
            "Returns all VET_APPOINTMENT tasks. "
            "Flags any past-due appointments based on due_date."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "Filter to a specific pet, or omit for all.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_health_note",
        "description": (
            "Appends a free-text health observation to a pet's health_notes list. "
            "Use this to record significant insights for later reference."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pet_name": {
                    "type": "string",
                    "description": "The pet to add the note to.",
                },
                "note": {
                    "type": "string",
                    "description": "The health observation to record (plain text).",
                },
            },
            "required": ["pet_name", "note"],
        },
    },
    _SCHEDULE_TASK_TOOL,
]


# ---------------------------------------------------------------------------
# Shared tool implementation mixin
# ---------------------------------------------------------------------------

class _ScheduleTaskMixin:
    """Provides _tool_schedule_task for agents that hold a Scheduler."""

    _scheduler: Scheduler

    def _tool_schedule_task(
        self,
        pet_name: str,
        task_type: str,
        description: str,
        duration: int,
        priority: int,
        frequency: str,
        preferred_hour: int | None = None,
        due_date: str | None = None,
    ) -> str:
        pet = next(
            (p for p in self._scheduler.owner.pets if p.name.lower() == pet_name.lower()),
            None,
        )
        if pet is None:
            return json.dumps({"error": f"Pet '{pet_name}' not found."})
        try:
            tt = TaskType(task_type)
            freq = Frequency(frequency)
        except ValueError as e:
            return json.dumps({"error": str(e)})

        ptime = time(preferred_hour, 0) if preferred_hour is not None else None
        ddate = date.fromisoformat(due_date) if due_date else None

        try:
            task = Task(
                task_type=tt,
                description=description,
                duration=duration,
                priority=priority,
                frequency=freq,
                preferred_time=ptime,
                due_date=ddate,
            )
        except ValueError as e:
            return json.dumps({"error": str(e)})

        self._scheduler.add_task(pet, task)
        logger.info("Task scheduled via agent: '%s' for %s", description, pet.name)
        return json.dumps({
            "success": True,
            "pet": pet.name,
            "description": description,
            "type": task_type,
            "frequency": frequency,
            "due_date": str(ddate) if ddate else None,
        })


# ---------------------------------------------------------------------------
# Care Plan Agent
# ---------------------------------------------------------------------------

class CarePlanAgent(_ScheduleTaskMixin):
    """Claude-powered agent that turns a natural-language request into a
    personalized daily care plan, and can also create tasks on the schedule.

    Each call to run() is independent (stateless). Prompt caching is applied
    to the system prompt so repeated calls within 5 minutes avoid re-encoding
    the full instruction prefix.
    """

    MODEL = "claude-opus-4-7"

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler
        self._client = anthropic.Anthropic()

    def run(self, user_message: str) -> str:
        """Drive the tool-use loop until end_turn and return the final text."""
        with agent_run("care_plan"):
            messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
            system = self._build_system_prompt()

            while True:
                logger.debug("Calling Claude (care_plan), messages=%d", len(messages))
                try:
                    response = self._client.messages.create(
                        model=self.MODEL,
                        max_tokens=4096,
                        system=system,
                        tools=CARE_PLAN_TOOLS,
                        messages=messages,
                    )
                except anthropic.AuthenticationError:
                    logger.error("Invalid API key")
                    raise
                except anthropic.RateLimitError as e:
                    logger.warning("Rate limited: %s", e)
                    raise
                except anthropic.APIError as e:
                    logger.error("API error: %s", e)
                    raise

                logger.info(
                    "Claude response stop_reason=%s input_tokens=%s output_tokens=%s",
                    response.stop_reason,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )

                if response.stop_reason == "end_turn":
                    text_blocks = [b.text for b in response.content if b.type == "text"]
                    return text_blocks[0] if text_blocks else ""

                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.debug("Tool call: %s input=%s", block.name, block.input)
                        result = self._dispatch_tool(block.name, block.input)
                        logger.debug("Tool result: %s", result[:200])
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "user", "content": tool_results})

    def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        dispatch = {
            "get_pending_tasks": self._tool_get_pending_tasks,
            "get_conflicts": self._tool_get_conflicts,
            "generate_daily_plan": self._tool_generate_daily_plan,
            "get_pet_info": self._tool_get_pet_info,
            "schedule_task": self._tool_schedule_task,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            logger.error("Unknown tool called: %s", tool_name)
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        return fn(**tool_input)

    def _tool_get_pending_tasks(self, pet_name: str | None = None) -> str:
        tasks = self._scheduler.filter_tasks(completed=False, pet_name=pet_name)
        result = []
        for task in tasks:
            owner_name = next(
                (p.name for p in self._scheduler.owner.pets if task in p.tasks),
                "unknown",
            )
            result.append({
                "pet": owner_name,
                "description": task.description,
                "type": task.task_type.value,
                "duration_min": task.duration,
                "priority": task.priority,
                "preferred_time": task.preferred_time.strftime("%H:%M") if task.preferred_time else None,
                "due_date": str(task.due_date) if task.due_date else None,
            })
        return json.dumps(result)

    def _tool_get_conflicts(self) -> str:
        conflicts = self._scheduler.detect_conflicts()
        if conflicts:
            logger.warning("Conflicts detected: %d", len(conflicts))
        return json.dumps({"conflicts": conflicts})

    def _tool_generate_daily_plan(self, available_hours: int) -> str:
        plan = self._scheduler.generate_plan(date.today(), available_hours)
        scheduled = [
            {
                "description": t.description,
                "type": t.task_type.value,
                "duration_min": t.duration,
                "priority": t.priority,
                "preferred_time": t.preferred_time.strftime("%H:%M") if t.preferred_time else None,
            }
            for t in plan.scheduled_tasks
        ]
        skipped_count = len(self._scheduler.filter_tasks(completed=False)) - len(scheduled)
        if skipped_count > 0:
            logger.warning("Tasks skipped in plan due to time limit: %d", skipped_count)
        return json.dumps({
            "date": str(plan.date),
            "scheduled_tasks": scheduled,
            "reasoning": plan.reasoning,
        })

    def _tool_get_pet_info(self, pet_name: str | None = None) -> str:
        pets = self._scheduler.owner.pets
        if pet_name:
            pets = [p for p in pets if p.name.lower() == pet_name.lower()]
        return json.dumps([
            {
                "name": p.name,
                "breed": p.breed,
                "age": p.age,
                "total_tasks": len(p.tasks),
                "pending_tasks": len(p.get_pending_tasks()),
            }
            for p in pets
        ])

    def _build_system_prompt(self) -> list[dict[str, Any]]:
        owner = self._scheduler.owner
        today = date.today()
        pet_lines = "\n".join(
            f"- {p.name}: {p.breed}, {p.age} years old, {len(p.tasks)} tasks registered"
            for p in owner.pets
        ) or "No pets registered yet."
        return [
            {"type": "text", "text": CARE_PLAN_SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": (
                    f"Today's date: {today.strftime('%A, %B %d, %Y')}\n"
                    f"Owner: {owner.name}\n\n"
                    f"Pets:\n{pet_lines}"
                ),
                "cache_control": {"type": "ephemeral"},
            },
        ]


# ---------------------------------------------------------------------------
# Health Advisor Agent
# ---------------------------------------------------------------------------

class HealthAdvisorAgent(_ScheduleTaskMixin):
    """Multi-turn Claude agent for pet health analysis.

    Conversation history is maintained in self._messages between calls to
    chat(), enabling follow-up questions without losing context.
    Call reset_conversation() to start fresh.
    """

    MODEL = "claude-opus-4-7"

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler
        self._client = anthropic.Anthropic()
        self._messages: list[dict[str, Any]] = []

    def chat(self, user_message: str) -> str:
        """Send one turn in the ongoing conversation. Returns Claude's reply."""
        with agent_run("health_advisor"):
            self._messages.append({"role": "user", "content": user_message})
            system = self._build_system_prompt()

            while True:
                logger.debug(
                    "Calling Claude (health_advisor), messages=%d", len(self._messages)
                )
                try:
                    response = self._client.messages.create(
                        model=self.MODEL,
                        max_tokens=4096,
                        system=system,
                        tools=HEALTH_ADVISOR_TOOLS,
                        messages=self._messages,
                    )
                except anthropic.AuthenticationError:
                    logger.error("Invalid API key")
                    raise
                except anthropic.RateLimitError as e:
                    logger.warning("Rate limited: %s", e)
                    raise
                except anthropic.APIError as e:
                    logger.error("API error: %s", e)
                    raise

                logger.info(
                    "Claude response stop_reason=%s input_tokens=%s output_tokens=%s",
                    response.stop_reason,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )

                if response.stop_reason == "end_turn":
                    text_blocks = [b.text for b in response.content if b.type == "text"]
                    final_text = text_blocks[0] if text_blocks else ""
                    self._messages.append({"role": "assistant", "content": final_text})
                    return final_text

                self._messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.debug("Tool call: %s input=%s", block.name, block.input)
                        result = self._dispatch_tool(block.name, block.input)
                        logger.debug("Tool result: %s", result[:200])
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                self._messages.append({"role": "user", "content": tool_results})

    def reset_conversation(self) -> None:
        self._messages = []
        logger.info("Health advisor conversation reset")

    def _dispatch_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        dispatch = {
            "get_pet_health_history": self._tool_get_pet_health_history,
            "get_medication_tasks": self._tool_get_medication_tasks,
            "get_vet_appointments": self._tool_get_vet_appointments,
            "add_health_note": self._tool_add_health_note,
            "schedule_task": self._tool_schedule_task,
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            logger.error("Unknown tool called: %s", tool_name)
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        return fn(**tool_input)

    def _tool_get_pet_health_history(self, pet_name: str) -> str:
        pet = next(
            (p for p in self._scheduler.owner.pets if p.name.lower() == pet_name.lower()),
            None,
        )
        if pet is None:
            return json.dumps({"error": f"Pet '{pet_name}' not found"})
        completed_tasks = [
            {
                "description": t.description,
                "type": t.task_type.value,
                "due_date": str(t.due_date) if t.due_date else None,
            }
            for t in pet.tasks
            if t.completed
        ]
        return json.dumps({
            "pet": pet.name,
            "health_notes": pet.health_notes,
            "completed_tasks": completed_tasks,
        })

    def _tool_get_medication_tasks(self, pet_name: str | None = None) -> str:
        today = date.today()
        result = []
        for pet in self._scheduler.owner.pets:
            if pet_name and pet.name.lower() != pet_name.lower():
                continue
            for task in pet.tasks:
                if task.task_type != TaskType.MEDICINE:
                    continue
                overdue = (
                    task.due_date is not None
                    and task.due_date < today
                    and not task.completed
                )
                if overdue:
                    logger.warning(
                        "Overdue medication: %s for %s", task.description, pet.name
                    )
                result.append({
                    "pet": pet.name,
                    "description": task.description,
                    "completed": task.completed,
                    "due_date": str(task.due_date) if task.due_date else None,
                    "overdue": overdue,
                    "priority": task.priority,
                })
        return json.dumps(result)

    def _tool_get_vet_appointments(self, pet_name: str | None = None) -> str:
        today = date.today()
        result = []
        for pet in self._scheduler.owner.pets:
            if pet_name and pet.name.lower() != pet_name.lower():
                continue
            for task in pet.tasks:
                if task.task_type != TaskType.VET_APPOINTMENT:
                    continue
                overdue = (
                    task.due_date is not None
                    and task.due_date < today
                    and not task.completed
                )
                if overdue:
                    logger.warning(
                        "Past-due vet appointment: %s for %s", task.description, pet.name
                    )
                result.append({
                    "pet": pet.name,
                    "description": task.description,
                    "completed": task.completed,
                    "due_date": str(task.due_date) if task.due_date else None,
                    "overdue": overdue,
                })
        return json.dumps(result)

    def _tool_add_health_note(self, pet_name: str, note: str) -> str:
        pet = next(
            (p for p in self._scheduler.owner.pets if p.name.lower() == pet_name.lower()),
            None,
        )
        if pet is None:
            return json.dumps({"error": f"Pet '{pet_name}' not found"})
        pet.health_notes.append(note)
        logger.info("Health note added for %s: %s", pet.name, note[:100])
        return json.dumps({"success": True, "pet": pet.name, "note": note})

    def _build_system_prompt(self) -> list[dict[str, Any]]:
        owner = self._scheduler.owner
        today = date.today()
        pet_lines = "\n".join(
            f"- {p.name}: {p.breed}, {p.age} years old"
            for p in owner.pets
        ) or "No pets registered yet."
        return [
            {"type": "text", "text": HEALTH_ADVISOR_SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": (
                    f"Today's date: {today.strftime('%A, %B %d, %Y')}\n"
                    f"Owner: {owner.name}\n\n"
                    f"Pets:\n{pet_lines}"
                ),
                "cache_control": {"type": "ephemeral"},
            },
        ]
