# Reliability and Evaluation
One of the things I added after coming back to this project was error logging. The log outputs are named under pawpal so they are more visible. Also the log outputs have correlation IDs so it is easier to see where an error occured and when doing what. API responses, errors, warnings, and debugs all get logged.

Here is an example of what the log trace looks like after asking the Care Plan Agent "Plan my day for Buddy, I have 5 hours free":
[INFO]  [run=care_plan-a3f8c201]  Agent run started: care_plan
[DEBUG] [run=care_plan-a3f8c201]  Calling Claude (care_plan), messages=1
[INFO]  [run=care_plan-a3f8c201]  Claude stop_reason=tool_use in=210 out=45
[DEBUG] [run=care_plan-a3f8c201]  Tool call: get_pending_tasks input={}
[DEBUG] [run=care_plan-a3f8c201]  Tool result: [{"pet": "Buddy", "description": ...}]
[DEBUG] [run=care_plan-a3f8c201]  Calling Claude (care_plan), messages=3
[INFO]  [run=care_plan-a3f8c201]  Claude stop_reason=end_turn in=380 out=120
[INFO]  [run=care_plan-a3f8c201]  Agent run ended: care_plan

# Reflection and Ethics
What are the limitations or biases in your system?
There are some obvious limitations with my system. For example if I ask it to book a vet appointment, the agent will not actually contact my vet's office and schedule and appointment. That level of autonomous agent activity is not in this app yet. 