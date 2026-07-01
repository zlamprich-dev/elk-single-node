# PKI guide

The framework uses two different trust domains:

1. **Service PKI** secures Elasticsearch, Kibana, Fleet Server, and Agent connections.
2. **Proxy PKI** validates HTTPS certificates re-signed by the corporate outbound proxy.

They may be issued by the same organization, but they are separate configuration inputs. Do not substitute one bundle for the other unless the PKI owner confirms they are identical.

## Certificate requests

Request separate leaf certificates for:

| Service | Required SAN | Required EKU |
|---|---|---|
| Elasticsearch | Exact `hostFqdn` | `serverAuth` and `clientAuth` because the current single certificate is also used for transport mTLS |
| Kibana | Exact `hostFqdn` | `serverAuth` |
| Fleet Server | Exact `hostFqdn` | `serverAuth` |

All three certificates contain the same DNS SAN because the services share the VM hostname and use different ports. Separate certificates and private keys are still preferred so compromise of one service key does not expose the others.

Do not rely only on a certificate Common Name. Modern hostname verification uses Subject Alternative Names.

The current framework uses the Elasticsearch certificate for both its HTTPS endpoint and node transport. Elastic transport peers act as TLS clients and servers, so a corporate certificate with EKUs must include both client and server authentication. If corporate policy cannot issue that combination, the framework needs separate Elasticsearch HTTP and transport certificates before deployment.

## File formats

- Certificates and CA chains: PEM.
- Private keys: unencrypted PKCS#8 or traditional PEM accepted by OpenSSL.
- Leaf certificate files should include the leaf first, followed by required intermediate certificates.
- `service-ca-chain.pem` should contain the trusted issuing CA chain.
- Do not include a CA private key anywhere in this repository or VM layout.

## Verify before deployment

Set local shell variables to the actual files and FQDN:

```bash
CERT=/data/elk-poc/pki/elasticsearch.crt
KEY=/data/elk-poc/pki/elasticsearch.key
CA=/data/elk-poc/pki/service-ca-chain.pem
FQDN=servername.us.company.com
```

Replace the example FQDN, then run:

```bash
openssl x509 -in "$CERT" -noout -subject -issuer -dates -ext subjectAltName -ext extendedKeyUsage
openssl verify -CAfile "$CA" "$CERT"
openssl x509 -in "$CERT" -noout -checkhost "$FQDN"
```

Verify certificate/key pairing without displaying private material:

```bash
openssl x509 -in "$CERT" -pubkey -noout \
  | openssl pkey -pubin -outform DER \
  | sha256sum

openssl pkey -in "$KEY" -pubout -outform DER \
  | sha256sum
```

The hashes must match.

Repeat for Kibana and Fleet Server.

## Permissions

```bash
sudo chown -R root:root /data/elk-poc/pki
sudo chmod 0700 /data/elk-poc/pki
sudo chmod 0644 /data/elk-poc/pki/*.crt /data/elk-poc/pki/*ca-chain.pem
sudo chmod 0600 /data/elk-poc/pki/*.key
```

Never commit `pki/`. Confirm Git ignores it:

```bash
git check-ignore -v pki/elasticsearch.key
```

## Chain-order symptoms

Possible symptoms of a missing or misordered chain include:

- `unable to get local issuer certificate`;
- `certificate signed by unknown authority`;
- Kibana repeatedly failing to connect to Elasticsearch;
- Fleet Server failing enrollment or Elasticsearch output validation.

Use `openssl s_client` after deployment:

```bash
openssl s_client \
  -connect servername.us.company.com:9200 \
  -servername servername.us.company.com \
  -CAfile /data/elk-poc/pki/service-ca-chain.pem \
  -verify_return_error </dev/null
```

Replace both example names with `hostFqdn`. A successful handshake must end with `Verify return code: 0 (ok)`.

## Renewal procedure

1. Obtain replacement files before the framework's 30-day minimum-validity threshold.
2. Validate SAN, EKU, chain, dates, and key pairing.
3. Replace source files atomically with the same names and permissions.
4. Run `sudo bin/elkctl preflight`.
5. Run `sudo bin/elkctl deploy` to render copies and restart affected services as required.
6. Verify each endpoint and Agent health.

Do not regenerate the service CA casually. Changing the CA requires coordinated trust changes for every enrolled Agent.
