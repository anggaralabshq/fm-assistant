---
description: Tampilkan plan, lalu jalankan di game setelah owner bilang ya
argument-hint: <plan id>
---
Use the fm-manager skill. `fm --json plan show $ARGUMENTS`, show its approval box (names, numbers, reason, backup
line) and wait for the owner's yes before `fm --json apply $ARGUMENTS`. Then report each action's status and answer.
