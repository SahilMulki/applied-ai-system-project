"""Unit tests for agents.py — all Anthropic API calls are mocked."""
import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from agents import CarePlanAgent, HealthAdvisorAgent, agent_run
from pawpal_system import Frequency, Owner, Pet, Scheduler, Task, TaskType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_scheduler() -> tuple[Scheduler, Pet]:
    owner = Owner(name="Test Owner")
    pet = Pet(name="Buddy", breed="Labrador", age=3)
    scheduler = Scheduler(owner=owner)
    owner.add_pet(pet)
    owner.set_schedule(scheduler)
    return scheduler, pet


def make_scheduler_with_tasks() -> tuple[Scheduler, Pet]:
    scheduler, pet = make_scheduler()
    walk = Task(
        task_type=TaskType.WALK,
        description="Morning walk",
        duration=30,
        priority=3,
    )
    med = Task(
        task_type=TaskType.MEDICINE,
        description="Heartworm pill",
        duration=5,
        priority=5,
        due_date=date.today(),
    )
    scheduler.add_task(pet, walk)
    scheduler.add_task(pet, med)
    return scheduler, pet


# ---------------------------------------------------------------------------
# CarePlanAgent — tool dispatch and implementations
# ---------------------------------------------------------------------------

class TestCarePlanAgentTools:
    def test_get_pending_tasks_returns_all(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_pending_tasks", {}))
        assert len(result) == 2

    def test_get_pending_tasks_filters_by_pet(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_pending_tasks", {"pet_name": "Buddy"}))
        assert all(t["pet"] == "Buddy" for t in result)

    def test_get_pending_tasks_unknown_pet_returns_empty(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_pending_tasks", {"pet_name": "Ghost"}))
        assert result == []

    def test_get_conflicts_no_overlap(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_conflicts", {}))
        assert result["conflicts"] == []

    def test_get_conflicts_with_overlap(self):
        from datetime import time
        scheduler, pet = make_scheduler()
        t1 = Task(TaskType.WALK, "Walk", 30, 3, preferred_time=time(8, 0))
        t2 = Task(TaskType.GROOMING, "Brush", 20, 2, preferred_time=time(8, 15))
        scheduler.add_task(pet, t1)
        scheduler.add_task(pet, t2)
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_conflicts", {}))
        assert len(result["conflicts"]) >= 1

    def test_generate_daily_plan_returns_structure(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("generate_daily_plan", {"available_hours": 8}))
        assert "scheduled_tasks" in result
        assert "reasoning" in result
        assert "date" in result

    def test_generate_daily_plan_schedules_both_tasks(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("generate_daily_plan", {"available_hours": 8}))
        assert len(result["scheduled_tasks"]) == 2

    def test_get_pet_info_all_pets(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_pet_info", {}))
        assert len(result) == 1
        assert result[0]["name"] == "Buddy"
        assert result[0]["total_tasks"] == 2

    def test_get_pet_info_specific_pet(self):
        scheduler, _ = make_scheduler()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_pet_info", {"pet_name": "Buddy"}))
        assert len(result) == 1

    def test_schedule_task_creates_task_on_pet(self):
        scheduler, pet = make_scheduler()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("schedule_task", {
            "pet_name": "Buddy",
            "task_type": "Vet Appointment",
            "description": "Annual checkup",
            "duration": 60,
            "priority": 5,
            "frequency": "As Needed",
            "due_date": "2026-05-10",
        }))
        assert result["success"] is True
        assert any(t.description == "Annual checkup" for t in pet.tasks)

    def test_schedule_task_appears_in_get_pending(self):
        scheduler, pet = make_scheduler()
        agent = CarePlanAgent(scheduler)
        agent._dispatch_tool("schedule_task", {
            "pet_name": "Buddy",
            "task_type": "Medicine",
            "description": "Heartworm pill",
            "duration": 5,
            "priority": 5,
            "frequency": "Daily",
        })
        pending = json.loads(agent._dispatch_tool("get_pending_tasks", {}))
        assert any(t["description"] == "Heartworm pill" for t in pending)

    def test_schedule_task_unknown_pet_returns_error(self):
        scheduler, _ = make_scheduler()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("schedule_task", {
            "pet_name": "Ghost",
            "task_type": "Walk",
            "description": "Evening walk",
            "duration": 30,
            "priority": 3,
            "frequency": "Daily",
        }))
        assert "error" in result

    def test_unknown_tool_returns_error(self):
        scheduler, _ = make_scheduler()
        agent = CarePlanAgent(scheduler)
        result = json.loads(agent._dispatch_tool("nonexistent_tool", {}))
        assert "error" in result


# ---------------------------------------------------------------------------
# HealthAdvisorAgent — tool dispatch and implementations
# ---------------------------------------------------------------------------

class TestHealthAdvisorAgentTools:
    def test_add_health_note_persists_on_pet(self):
        scheduler, pet = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        agent._dispatch_tool(
            "add_health_note", {"pet_name": "Buddy", "note": "Seems lethargic after walks"}
        )
        assert "Seems lethargic after walks" in pet.health_notes

    def test_add_health_note_multiple_notes(self):
        scheduler, pet = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        agent._dispatch_tool("add_health_note", {"pet_name": "Buddy", "note": "Note 1"})
        agent._dispatch_tool("add_health_note", {"pet_name": "Buddy", "note": "Note 2"})
        assert len(pet.health_notes) == 2

    def test_add_health_note_unknown_pet_returns_error(self):
        scheduler, _ = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(
            agent._dispatch_tool("add_health_note", {"pet_name": "Ghost", "note": "test"})
        )
        assert "error" in result

    def test_get_pet_health_history_includes_completed_tasks(self):
        scheduler, pet = make_scheduler_with_tasks()
        pet.tasks[0].mark_complete()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(
            agent._dispatch_tool("get_pet_health_history", {"pet_name": "Buddy"})
        )
        assert result["pet"] == "Buddy"
        assert len(result["completed_tasks"]) == 1

    def test_get_pet_health_history_includes_health_notes(self):
        scheduler, pet = make_scheduler()
        pet.health_notes.append("Good energy today")
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(
            agent._dispatch_tool("get_pet_health_history", {"pet_name": "Buddy"})
        )
        assert "Good energy today" in result["health_notes"]

    def test_get_pet_health_history_not_found(self):
        scheduler, _ = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(
            agent._dispatch_tool("get_pet_health_history", {"pet_name": "Nonexistent"})
        )
        assert "error" in result

    def test_get_medication_tasks_filters_type(self):
        scheduler, _ = make_scheduler_with_tasks()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_medication_tasks", {}))
        assert len(result) == 1
        assert result[0]["description"] == "Heartworm pill"

    def test_get_medication_tasks_flags_overdue(self):
        scheduler, pet = make_scheduler()
        overdue_task = Task(
            task_type=TaskType.MEDICINE,
            description="Old pill",
            duration=5,
            priority=4,
            due_date=date.today() - timedelta(days=2),
        )
        scheduler.add_task(pet, overdue_task)
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_medication_tasks", {}))
        assert result[0]["overdue"] is True

    def test_get_vet_appointments_empty(self):
        scheduler, _ = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_vet_appointments", {}))
        assert result == []

    def test_get_vet_appointments_flags_past_due(self):
        scheduler, pet = make_scheduler()
        appt = Task(
            task_type=TaskType.VET_APPOINTMENT,
            description="Annual checkup",
            duration=60,
            priority=5,
            due_date=date.today() - timedelta(days=1),
        )
        scheduler.add_task(pet, appt)
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(agent._dispatch_tool("get_vet_appointments", {}))
        assert result[0]["overdue"] is True

    def test_schedule_task_creates_vet_appointment(self):
        scheduler, pet = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(agent._dispatch_tool("schedule_task", {
            "pet_name": "Buddy",
            "task_type": "Vet Appointment",
            "description": "Dental cleaning",
            "duration": 90,
            "priority": 4,
            "frequency": "As Needed",
            "due_date": "2026-06-01",
        }))
        assert result["success"] is True
        assert any(t.description == "Dental cleaning" for t in pet.tasks)

    def test_reset_conversation_clears_history(self):
        scheduler, _ = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        agent._messages = [{"role": "user", "content": "Hello"}]
        agent.reset_conversation()
        assert agent._messages == []

    def test_unknown_tool_returns_error(self):
        scheduler, _ = make_scheduler()
        agent = HealthAdvisorAgent(scheduler)
        result = json.loads(agent._dispatch_tool("bad_tool", {}))
        assert "error" in result


# ---------------------------------------------------------------------------
# Logging / correlation
# ---------------------------------------------------------------------------

class TestLogging:
    def test_agent_run_yields_labeled_run_id(self):
        with agent_run("test_label") as run_id:
            assert "test_label" in run_id

    def test_agent_run_ids_are_unique(self):
        with agent_run("test") as id1:
            pass
        with agent_run("test") as id2:
            pass
        assert id1 != id2

    def test_agent_run_reraises_exceptions(self):
        with pytest.raises(RuntimeError, match="boom"):
            with agent_run("test"):
                raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# CarePlanAgent.run() — mocked API round-trip
# ---------------------------------------------------------------------------

class TestCarePlanAgentRun:
    def _make_end_turn_response(self, text: str) -> MagicMock:
        response = MagicMock()
        response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text
        response.content = [text_block]
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        return response

    def _make_tool_use_response(
        self, tool_name: str, tool_id: str, tool_input: dict
    ) -> MagicMock:
        response = MagicMock()
        response.stop_reason = "tool_use"
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = tool_name
        tool_block.id = tool_id
        tool_block.input = tool_input
        response.content = [tool_block]
        response.usage.input_tokens = 80
        response.usage.output_tokens = 20
        return response

    @patch("agents.anthropic.Anthropic")
    def test_run_end_turn_immediately(self, mock_anthropic_cls):
        scheduler, _ = make_scheduler()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_end_turn_response(
            "Here is your plan!"
        )
        agent = CarePlanAgent(scheduler)
        result = agent.run("Plan my day")
        assert result == "Here is your plan!"

    @patch("agents.anthropic.Anthropic")
    def test_run_single_tool_call_then_end_turn(self, mock_anthropic_cls):
        scheduler, _ = make_scheduler_with_tasks()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            self._make_tool_use_response("get_pending_tasks", "tu_001", {}),
            self._make_end_turn_response("Here is your plan with tasks!"),
        ]
        agent = CarePlanAgent(scheduler)
        result = agent.run("What tasks do I have?")
        assert result == "Here is your plan with tasks!"
        assert mock_client.messages.create.call_count == 2

    @patch("agents.anthropic.Anthropic")
    def test_run_raises_authentication_error(self, mock_anthropic_cls):
        import anthropic as anthropic_module
        scheduler, _ = make_scheduler()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic_module.AuthenticationError(
            message="Invalid key", response=MagicMock(), body={}
        )
        agent = CarePlanAgent(scheduler)
        with pytest.raises(anthropic_module.AuthenticationError):
            agent.run("plan my day")


# ---------------------------------------------------------------------------
# HealthAdvisorAgent.chat() — mocked API round-trip
# ---------------------------------------------------------------------------

class TestHealthAdvisorAgentChat:
    def _make_end_turn_response(self, text: str) -> MagicMock:
        response = MagicMock()
        response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text
        response.content = [text_block]
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        return response

    @patch("agents.anthropic.Anthropic")
    def test_chat_appends_to_message_history(self, mock_anthropic_cls):
        scheduler, _ = make_scheduler()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_end_turn_response(
            "Buddy looks healthy!"
        )
        agent = HealthAdvisorAgent(scheduler)
        agent.chat("How is Buddy doing?")
        assert len(agent._messages) == 2
        assert agent._messages[0]["role"] == "user"
        assert agent._messages[1]["role"] == "assistant"

    @patch("agents.anthropic.Anthropic")
    def test_chat_multi_turn_preserves_context(self, mock_anthropic_cls):
        scheduler, _ = make_scheduler()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            self._make_end_turn_response("Buddy seems fine."),
            self._make_end_turn_response("Yes, once a week is fine."),
        ]
        agent = HealthAdvisorAgent(scheduler)
        agent.chat("How is Buddy?")
        agent.chat("Should I walk him more?")
        assert len(agent._messages) == 4
