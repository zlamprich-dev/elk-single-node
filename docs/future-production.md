# Deferred production work

The POC intentionally does not implement:

- Durable NFS or S3 snapshots and restore exercises.
- Automated upgrades or downgrade recovery.
- Image digest locking or signature policy enforcement.
- Remote Linux and Windows enrollment kits.
- Custom retention and capacity sizing.
- High availability or replica protection.
- Certificate renewal automation.
- Alert routing and operational ownership.
- Vault-backed secret materialization.

These require a separate design after the POC is accepted. A production request must not relabel this single-VM demonstration as highly available.

