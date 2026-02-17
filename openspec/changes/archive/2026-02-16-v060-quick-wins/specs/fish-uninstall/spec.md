## ADDED Requirements

### Requirement: Fish integration uninstall flag
The `shoal setup fish` command SHALL accept a `--uninstall` flag that removes all fish integration files previously installed by the setup command. The uninstall SHALL print each file being removed.

#### Scenario: Uninstall with existing installation
- **WHEN** user runs `shoal setup fish --uninstall` and fish integration files exist
- **THEN** the system removes the bootstrap, completions, quick-attach, and conf.d sourcer files, printing each removal

#### Scenario: Uninstall with no existing installation
- **WHEN** user runs `shoal setup fish --uninstall` and no fish integration files exist
- **THEN** the system prints a message indicating nothing to remove and exits cleanly

#### Scenario: Uninstall respects XDG_CONFIG_HOME
- **WHEN** user runs `shoal setup fish --uninstall` with `XDG_CONFIG_HOME` set
- **THEN** the system looks for and removes files from the XDG-derived fish config directory
