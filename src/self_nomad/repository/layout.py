from textwrap import dedent
from uuid import uuid4


def manifest_template(name: str, description: str | None = None) -> str:
    description_line = f'  description: "{description}"\n' if description else ""
    return dedent(
        f'''\
        schema_version: 1

        self:
          id: "{uuid4()}"
          name: "{name}"
        {description_line}content:
          instructions: "identity/instructions.md"
          persona: "identity/persona.md"
          identity: "identity/identity.md"
          user_profile: "identity/user.md"
          long_term_memory: "memory/MEMORY.md"
          daily_memory: "memory/daily"
          knowledge: "memory/knowledge"
          skills: "skills"
          tool_notes: "tools/notes.md"
          workflows: "workflows"
          evaluations: "evals"

        skill_format: "agent-skills"
        policy: "policy/policy.yaml"

        adapters:
          hermes:
            enabled: true
          openclaw:
            enabled: true
        '''
    )


POLICY_TEMPLATE = """\
schema_version: 1

approval:
  default: required
  protected_paths:
    - "self-nomad.yaml"
    - "policy/**"
    - "identity/instructions.md"
    - "identity/persona.md"

limits:
  maximum_file_bytes: 1048576
  maximum_proposal_files: 100

validation:
  strict_schema: true
  reject_symlinks: true
  scan_for_secrets: true
  execute_repository_tests: false
"""


ARTIFACT_TEMPLATES = {
    "identity/instructions.md": "# Instructions\n",
    "identity/persona.md": "# Persona\n",
    "identity/identity.md": "# Identity\n",
    "identity/user.md": "# User\n",
    "memory/MEMORY.md": "# Memory\n",
    "tools/notes.md": "# Tool notes\n",
}
