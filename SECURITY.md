# Security policy

Do not include private agent repositories, credentials, transcripts, or other
sensitive data in public vulnerability reports.

The project treats manifest paths and repository content as untrusted. It does
not manage credentials or session databases and does not execute tests or
scripts found in a self repository. Git history retains deleted content; rotate
credentials and rewrite history if a secret is ever committed.

Until a private reporting channel is published, open a minimal GitHub security
advisory without sensitive reproduction data.

All Git commands managed by self-nomad disable repository and global hooks.
Configured Git clean/smudge/process filters remain trusted user infrastructure;
do not use self-nomad with an untrusted filter executable. Proposal approval
binds the resulting full Git tree and exact declared diff.
