# Job Transitions

Refactor Job.send(event) around a single transition definition, preserving new -> running on start, running -> done on finish, and new/running -> cancelled on cancel. Add pause from running -> paused, resume from paused -> running, and cancel from paused -> cancelled. Invalid events raise ValueError without changing state/history. Each successful event appends (old_state, event, new_state) to history. done and cancelled are terminal. Keep initial state new and an independent history per instance.

Run `python -m unittest discover -s tests -q` from this directory.
