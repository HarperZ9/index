# Privacy

This local profile reads only submitted paths under the workspace selected at
launch. Tool output is returned to the connected client and its chosen model.
No publisher service, telemetry endpoint, inference engine, or credential store
is used by this profile. Do not include confidential data in the selected
workspace unless that client and model are authorized to receive it.

The optional launch flag `--state-directory` grants reads and writes in one
existing private state directory for cached maps and existing job
receipts. Inspection can update recovery metadata; cancellation writes a request.
Tool arguments and inherited environment variables cannot select that directory.
