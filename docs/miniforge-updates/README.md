# Miniforge base updates

This is the index for user-facing package change lists from the base rollout.
Each installation has its own record. A list shows package additions, removals,
version changes, build changes and unchanged packages; it does not change or
describe separate user/baseline environments.

No installation-specific reports have been added here yet. After an installation
passes rollout review, the maintainer should add a link to its reviewed change
list, identifying the machine/shared installation, GCC/Intel setup and deployment
date. Use the actual deployment date, not the date a historical report was exported.
If a shared installation serves several machines, identify that shared scope.

Users can consult the linked `README.md` for the readable list or `packages.csv`
for the table. `manifest.json` records evidence/coverage and the recorded rollout
status. `verified-installed` identifies a verified installed package set;
`limited-installed-summary` identifies incomplete historical detail. A
`candidate-only` report is headed **NOT INSTALLED** and must not be listed as a
completed update. Version changes can include downgrades selected for compatibility.

Maintainers: generate/recover reports using the
[base rollout handoff](../miniforge-base-rollout.md#generate-the-user-facing-package-change-list).
Copy only the four generated change-list files to this area or the approved
internal documentation location, then add the final accessible link here. Keep
private logs and permission/owner reports in the maintenance record. Publication
and user notification are separate steps; the script does neither automatically.
