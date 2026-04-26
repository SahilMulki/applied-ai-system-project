The original project was PawPal+. PawPal is a smart pet care management system to help owners take care of their pets. The app helps owners track things for their pets like feedings, walks, appointments, etc.

# Title and Summary

This project builds on the original PawPal+ app. I added two agents, a Care Plan Agent, and a Health Advisor Agent. The user can talk to these agents in natural language and the agents will autonomously do things like schedule an appointment or create a care plan. I also added more error logging to help to evals and testing. These new features matter because they make the app more helpful for owners.

# Architecture Overview

The diagram helps to show the agentic workflow of this app. You can see how when the user chats with an agent, the agent is capable of independently calling tools that provide it with the information it needs to be able to do things like schedule an appointment are create a personalized schedule. You can also see that I am using the Claude API for the agents.

# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.
