# Security policy

Do not include private agent repositories, credentials, transcripts, or other
sensitive data in public vulnerability reports.

The project treats manifest paths and repository content as untrusted. It does
not manage credentials or session databases and does not execute tests or
scripts found in a self repository. Git history retains deleted content; rotate
credentials and rewrite history if a secret is ever committed.

Until a private reporting channel is published, open a minimal GitHub security
advisory without sensitive reproduction data.

