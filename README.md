The original project was PawPal+. PawPal is a smart pet care management system to help owners take care of their pets. The app helps owners track things for their pets like feedings, walks, appointments, etc.

# Title and Summary

This project builds on the original PawPal+ app. I added two agents, a Care Plan Agent, and a Health Advisor Agent. The user can talk to these agents in natural language and the agents will autonomously do things like schedule an appointment or create a care plan. I also added more error logging to help to evals and testing. These new features matter because they make the app more helpful for owners.

# Architecture Overview

The diagram helps to show the agentic workflow of this app. You can see how when the user chats with an agent, the agent is capable of independently calling tools that provide it with the information it needs to be able to do things like schedule an appointment are create a personalized schedule. You can also see that I am using the Claude API for the agents.

# Setup Instructions

Prerequisites
Python 3.11 or 3.12
An Anthropic API key from console.anthropic.com

1. Create and activate a virtual environment

python -m venv .venv
source .venv/bin/activate # macOS/Linux
.venv\Scripts\activate # Windows 2. Install dependencies

pip install -r requirements.txt

3. Add your API key
   Create a .env file in the project root:

ANTHROPIC_API_KEY=sk-ant-...
The app loads it automatically — no other config needed.

4. Run the app

streamlit run app.py
Opens at http://localhost:8501.

# Sample Interactions

Chatting with the Care Plan Agent:
User: "Book a vet checkup for Daisy next week"
Care Plan Agent: "Done, John! 🐾 I've booked Daisy's vet checkup for Monday, May 4, 2026 (60 minutes). Check the Schedule tab to see it and adjust the time if needed."

Chatting with the Health Advisor Agent:
User: "Schedule a flea treatment for Daisy"
Health Advisor Agent: "Done! 🐾 I've scheduled a monthly flea treatment for Daisy. You can find it in the Schedule tab.

A few quick tips:

Apply the treatment to dry skin at the back of her neck/between her shoulder blades where she can't lick it off.
Avoid bathing her for 48 hours before and after application for best absorption.
Keep an eye out for any skin irritation at the application site.
Would you like me to also set a specific start date, or schedule a tick preventative alongside it?"

# Design Decisions

In terms of the base structure of the app it is built according the specifications laid out in the project description. I iterated on the layout and appearance of the app to make the app easier to use. I considered adding functionality for people looking to buy a pet or pet supplies, but I figured the trade off wasn't worth it. It made more sense that this app was solely focused on supporting pet owners in tracking their pets activities and needs.

# Testing Summary

I think the overall layout and structure of the app really worked. It makes a lot of sense and I feel like its very intuitive. Some of the features didn't work for a while so I had to keep iterating until they got to a point where I felt like they did what I wanted. Like for example I had an issue where the agent would continuously get the date wrong when booking an appointment.

# Reflection

This project helped me understand agents and agentic workflows better. Also it was a good experience to be able to go back to an old project and think of ways I could make it better.

# Systems Architecture Diagram

The diagram is in the assets folder.

# Demo Walkthrough:

https://www.loom.com/share/e6708e13d9364516998e326e448a4f27
