# Glossary

**CA (Certificate Authority)**  
An authority that signs certificates. Clients trust a server certificate by validating its chain to a trusted CA.

**Data stream**  
Elasticsearch’s abstraction for continuously generated time-series data such as logs and metrics. A data stream uses hidden backing indices.

**Elasticsearch**  
The datastore and search engine. Agents send events to Elasticsearch, normally over HTTPS port 9200.

**Elastic Agent**  
The process that collects logs and metrics and receives policy from Fleet Server. In this POC one Agent monitors the RHEL host.

**EKU (Extended Key Usage)**  
A certificate extension restricting how a certificate may be used, such as `serverAuth` or `clientAuth`.

**Fleet**  
The Kibana application used to define Agent policies, integrations, enrollment tokens, and outputs.

**Fleet Server**  
The service through which enrolled Agents receive policy and report status. Agents connect to it on HTTPS port 8220.

**FQDN (Fully Qualified Domain Name)**  
A complete DNS name such as `servername.us.company.com`. This POC uses the VM FQDN for all three HTTPS services, distinguished by port, and requires it in every service certificate SAN.

**Integration**  
A versioned Elastic package containing Agent inputs, ingest pipelines, mappings, and dashboards for a data source.

**Kibana**  
The web interface for Elastic. It provides search, dashboards, Fleet, and administrative tools, normally on HTTPS port 5601.

**mTLS (Mutual TLS)**  
TLS where both peers present and validate certificates. Elasticsearch transport uses mTLS between nodes.

**PEM**  
A text encoding used for certificates and private keys, recognizable by `-----BEGIN ...-----` markers.

**Podman**  
The daemonless container engine used by this framework on RHEL.

**Quadlet**  
A Podman-native systemd configuration file. `.container` and `.network` files are converted into systemd services by Podman’s generator.

**SAN (Subject Alternative Name)**  
Certificate fields containing the DNS names or IP addresses for which the certificate is valid.

**SELinux**  
RHEL’s mandatory access-control system. Unix permissions alone do not guarantee that a container may read a host file.

**System integration**  
The Elastic integration that collects operating-system logs and metrics.

**Transport port 9300**  
Elasticsearch’s internal node protocol. It is not a browser or Agent endpoint and is not published by this framework.

**`NO_PROXY`**  
A list of hosts and networks that bypass an HTTP proxy. Internal Elastic traffic must not be sent through the corporate outbound proxy.
