from textwrap import dedent
from uuid import uuid4


def manifest_template(name: str, description: str | None = None) -> str:
    # Description is inserted after dedent. Putting a shorter line inside the
    # indented literal would shrink the common indent and break the document.
    text = dedent(
        f'''\
        schema_version: 1

        self:
          id: "{uuid4()}"
          name: "{name}"
        content:
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
    if not description:
        return text
    if "\n" in description or '"' in description:
        raise ValueError("description cannot contain quotes or newlines")
    return text.replace(
        f'  name: "{name}"\n',
        f'  name: "{name}"\n  description: "{description}"\n',
        1,
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
    "memory/PUBLISH.md": (
        "# Publishable memory\n\n"
        "Facts copied here may be included in a specialist pack. "
        "`memory/MEMORY.md` is a personal dump and is never packed as specialist.\n"
    ),
    "tools/notes.md": "# Tool notes\n",
}
