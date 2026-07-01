# POC acceptance checklist

- [ ] `elkctl preflight` returns zero failures.
- [ ] Elasticsearch, Kibana, Fleet Server, and the Agent services are active.
- [ ] Elasticsearch cluster health is green or has an explained transient warning.
- [ ] Kibana opens over HTTPS without bypassing certificate validation.
- [ ] Fleet Server and the local Agent report healthy.
- [ ] System metrics appear in Kibana.
- [ ] RHEL journal or system log events appear in Discover.
- [ ] The Agent remains enrolled after `elkctl restart`.
- [ ] Only ports 5601, 8220, and 9200 are published.
- [ ] Elasticsearch transport port 9300 is not published.
- [ ] SELinux remains enforcing.
- [ ] No container is privileged and no Podman socket is mounted.
- [ ] Secrets are absent from Git and normal command output.

This checklist accepts that the single VM has no high availability and no durable backup.
