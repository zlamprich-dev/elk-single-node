# Manual GitLab transfer

GitLab is only the transport mechanism for this POC. No runner, pipeline, or CI/CD configuration is required.

## Publish the project from the development workstation

Create an empty private repository in enterprise GitLab. Do not initialize it with a README, because this project already has Git history and files.

Before pushing, verify that local configuration and credentials are not tracked:

```bash
git status --short
git check-ignore config/stack.json pki/elasticsearch.key secrets/elastic-password runtime/
git grep -nE 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|password|enrollment.token'
```

Review every match from `git grep`; documentation may contain harmless words, but no real credential or private-key block may be present.

Add the enterprise repository as a separate remote and push the current branch:

```bash
git remote add enterprise <enterprise-gitlab-url>
git branch --show-current
git push -u enterprise HEAD
```

Using a separate remote preserves the existing `origin`. If a remote named `enterprise` already exists, inspect it with `git remote -v` instead of replacing it blindly.

## Clone on the RHEL VM

Use the final deployment path so generated state is created under `/data/elk-poc`:

```bash
sudo install -d -m 0750 -o "$USER" -g "$(id -gn)" /data/elk-poc
git clone <enterprise-gitlab-url> /data/elk-poc
cd /data/elk-poc
```

Authentication depends on corporate GitLab policy. Use an approved SSH key, credential helper, or short-lived access token. Do not put a token in the clone URL, shell history, repository, or `config/stack.json`.

Continue with the [first deployment walkthrough](first-deployment.md). Site configuration, PKI, runtime data, and secrets are created on the VM and remain outside Git.
