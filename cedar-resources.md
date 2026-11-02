# Cedar Resources

An organized guide to the Cedar policy language ecosystem.

**Status checked:** 2026-09-21

## How to read the activity labels

For GitHub projects, **Last updated** is the repository's most recent push date reported by GitHub when this list was checked. Activity labels describe maintenance recency, not quality, security, popularity, or production readiness.

| Label | Meaning |
| --- | --- |
| 🟢 Active | Updated within the last 90 days |
| 🟡 Maintained | Updated 3–12 months ago |
| 🟠 Quiet | Updated 1–2 years ago |
| 🔴 Dormant | No update for more than 2 years |
| ⚫ Archived | Repository is archived or explicitly superseded |
| — | Activity cannot be inferred meaningfully from a webpage or commercial service |

The labels are deliberately mechanical so the list can be refreshed without subjective judgments. A recent push is not an endorsement. Evaluate release history, issue response, security posture, licensing, and compatibility before adopting any project.

## 1. Start here

These are the shortest paths to understanding and trying Cedar.

| Resource | What it is | Last updated | Activity |
| --- | --- | ---: | :---: |
| [Cedar website](https://www.cedarpolicy.com/) | Project overview and entry point | — | — |
| [Cedar documentation](https://docs.cedarpolicy.com/) | Language guide, schema, authorization, validation, and best practices | 2026-09-16 ([source](https://github.com/cedar-policy/cedar-docs)) | 🟢 |
| [Cedar Playground](https://www.cedarpolicy.com/en/playground) | Browser-based policy editor and evaluator | — | — |
| [Cedar examples](https://github.com/cedar-policy/cedar-examples) | Official example policies, schemas, entities, and requests | 2026-09-16 | 🟢 |
| [Cedar repository](https://github.com/cedar-policy/cedar) | Canonical Rust implementation, CLI, crates, and release history | 2026-09-18 | 🟢 |
| [Cedar community](https://github.com/cedar-policy/cedar-community) | Community meeting notes and participation information | 2026-08-18 | 🟢 |

## 2. Language design, specification, and assurance

Use these when you need the precise language semantics, formal model, compatibility direction, or implementation assurance.

| Resource | What it is | Last updated | Activity |
| --- | --- | ---: | :---: |
| [Cedar specification](https://github.com/cedar-policy/cedar-spec) | Definitional implementation and differential random testing utilities | 2026-09-18 | 🟢 |
| [Cedar RFCs](https://github.com/cedar-policy/rfcs) | Proposed and accepted language or ecosystem changes | 2026-07-16 | 🟢 |
| [Cedar integration tests](https://github.com/cedar-policy/cedar-integration-tests) | Cross-implementation compatibility tests | 2026-09-16 | 🟢 |
| [Verified Cedar JSON parser](https://github.com/cedar-policy/cedar-json-parser) | JSON parser verified with Verus | 2026-09-09 | 🟢 |
| [Cedar authorization](https://github.com/cedar-policy/cedar-authorization) | Work related to authorization APIs and integration patterns | 2026-08-02 | 🟢 |

## 3. Engines, SDKs, and language bindings

### Official

| Project | Language/runtime | Implementation model | Last updated | Activity |
| --- | --- | --- | ---: | :---: |
| [cedar-policy](https://github.com/cedar-policy/cedar) | Rust | Canonical Cedar engine and crates | 2026-09-18 | 🟢 |
| [cedar-java](https://github.com/cedar-policy/cedar-java) | Java | Bindings to the native Cedar engine | 2026-09-14 | 🟢 |
| [cedar-go](https://github.com/cedar-policy/cedar-go) | Go | Native Go implementation | 2026-07-15 | 🟢 |

### Community

| Project | Language/runtime | Implementation model | Last updated | Activity |
| --- | --- | --- | ---: | :---: |
| [Cedarling](https://github.com/JanssenProject/jans/tree/main/jans-cedarling) | Rust, WASM, Java, Python, Go | Embeddable Cedar PDP with token-aware authorization; part of the Janssen monorepo | 2026-09-21 ([repository](https://github.com/JanssenProject/jans)) | 🟢 |
| [cedar-py](https://github.com/k9securityio/cedar-py) | Python | Python bindings to Cedar | 2026-09-14 | 🟢 |
| [cedar-policy-rb](https://github.com/elct9620/cedar-policy-rb) | Ruby | Ruby bindings to Cedar | 2026-09-15 | 🟢 |
| [monocloud-cedar-dotnet](https://github.com/monocloud/monocloud-cedar-dotnet) | .NET | .NET bindings modeled on the Java integration | 2026-07-15 | 🟢 |
| [CedarDotNet](https://github.com/jamiewinder/CedarDotNet) | .NET | .NET Cedar library | 2025-11-21 | 🟡 |
| [Joffref/cedar](https://github.com/Joffref/cedar) | Go/WASM | Go bindings using an embedded WASM engine | 2023-11-17 | 🔴 |
| [cedargo](https://github.com/iann0036/cedargo) | Go/CGO | Go bindings using CGO | 2024-03-12 | 🔴 |

## 4. Run and deploy Cedar

Choose among managed authorization, a local or sidecar service, an embeddable PDP, and platform-specific enforcement.

| Project or service | Deployment model | Notes | Last updated | Activity |
| --- | --- | --- | ---: | :---: |
| [Amazon Verified Permissions](https://aws.amazon.com/verified-permissions/) | AWS managed service | Managed authorization service built on Cedar | — | — |
| [Cedar local agent](https://github.com/cedar-policy/cedar-local-agent) | Local service/agent | Official local Cedar evaluation component | 2026-05-07 | 🟢 |
| [Cedar Agent](https://github.com/permitio/cedar-agent) | Standalone service/sidecar | REST service for deploying and running Cedar | 2025-10-16 | 🟡 |
| [Cedrus](https://github.com/stratusmedia/cedrus) | Standalone REST service | Community Cedar policy server | 2026-09-08 | 🟢 |
| [Cedarling](https://github.com/JanssenProject/jans/tree/main/jans-cedarling) | Embedded library, WASM, or sidecar | Token-aware PDP for applications, services, and edge environments | 2026-09-21 | 🟢 |
| [Cedar for Kubernetes](https://github.com/cedar-policy/cedar-access-control-for-k8s) | Kubernetes authorization and admission | Unified Cedar policies for API authorization and admission validation | 2026-08-10 | 🟢 |
| [Authorization for Express.js](https://github.com/cedar-policy/authorization-for-expressjs) | Node.js middleware/example | Cedar authorization integration for Express applications | 2026-08-02 | 🟢 |
| [Permit.io](https://www.permit.io/) | Commercial authorization platform | Cedar support alongside policy administration and distribution | — | — |
| [OPAL](https://github.com/permitio/opal) | Policy and data distribution | Real-time policy/data updates for policy agents, including Cedar-related deployments | 2026-09-17 | 🟢 |

## 5. AI-agent authorization

This area is moving quickly, so consumers should check open issues and releases in addition to the dates below.

| Resource | What it is | Last updated | Activity |
| --- | --- | ---: | :---: |
| [Cedar for Agents](https://github.com/cedar-policy/cedar-for-agents) | Official work on Cedar schemas, patterns, and authorization for AI agents | 2026-09-21 | 🟢 |
| [Cedarling](https://github.com/JanssenProject/jans/tree/main/jans-cedarling) | Embedded PDP suited to agent, workload, browser, mobile, and service authorization | 2026-09-21 | 🟢 |
| [Cedar MCP Server](https://github.com/Pigius/cedar-mcp-server) | MCP tools for validating, authorizing, comparing, and planning Cedar policy changes | 2026-05-23 | 🟢 |

## 6. Authoring and editor tools

| Project | Environment | Last updated | Activity |
| --- | --- | ---: | :---: |
| [VS Code extension](https://github.com/cedar-policy/vscode-cedar) · [Marketplace](https://marketplace.visualstudio.com/items?itemName=cedar-policy.vscode-cedar) | Visual Studio Code | 2026-09-15 | 🟢 |
| [Cedar Monaco Editor](https://github.com/cedar-policy/cedar-monaco-editor) | Browser/React applications | 2026-06-08 | 🟢 |
| [highlight.js support](https://github.com/cedar-policy/highlightjs-cedar) | Web syntax highlighting | 2026-09-10 | 🟢 |
| [Prism support](https://github.com/cedar-policy/prism-cedar) | Web syntax highlighting | 2026-09-10 | 🟢 |
| [Tree-sitter grammar](https://github.com/chrnorm/tree-sitter-cedar) | Editors using Tree-sitter | 2024-07-03 | 🔴 |
| [Zed extension](https://github.com/chrnorm/zed-cedar) | Zed | 2024-05-13 | 🔴 |
| [Vim plugin](https://github.com/Dzordzu/vim-cedar) | Vim | 2023-09-22 | 🔴 |

## 7. Examples and interactive learning

| Resource | Best use | Last updated | Activity |
| --- | --- | ---: | :---: |
| [Cedar Playground](https://www.cedarpolicy.com/en/playground) | Try requests, entities, schemas, and policies without installing anything | — | — |
| [Official examples](https://github.com/cedar-policy/cedar-examples) | Learn common modeling and policy patterns from runnable examples | 2026-09-16 | 🟢 |
| [OpenPARC Playground](https://playground.openparc.dev/) | Independent browser playground | — | — |
| [AuthZEN interface for Verified Permissions](https://github.com/aws-samples/sample-authzen-interface-verified-permissions) | Reference implementation connecting the OpenID AuthZEN protocol to Amazon Verified Permissions | 2026-03-26 | 🟡 |
| [ASP.NET Core authorization provider](https://github.com/aws-samples/amazon-verified-permissions-asp-dotnet-core-custom-auth-policy-provider) | Custom ASP.NET Core authorization policy provider backed by Verified Permissions | 2026-07-28 | 🟢 |
| [RBAC-to-PBAC migration sample](https://github.com/aws-samples/sample-app-migrate-access-rbac-to-pbac-with-verified-permissions) | Example migration from role-based to policy-based authorization | 2026-01-30 | 🟡 |

## 8. Research and foundational reading

These resources are intentionally organized by topic rather than “activity.” Articles do not become unmaintained in the same way as software; the publication year is a better freshness signal.

### Language design and automated reasoning

- [How we designed Cedar to be intuitive to use, fast, and safe](https://aws.amazon.com/blogs/security/how-we-designed-cedar-to-be-intuitive-to-use-fast-and-safe/) — AWS Security Blog, 2023.
- [How we built Cedar with automated reasoning and differential testing](https://www.amazon.science/blog/how-we-built-cedar-with-automated-reasoning-and-differential-testing) — Amazon Science, 2023.
- [Using open source Cedar to write and enforce custom authorization policies](https://aws.amazon.com/blogs/opensource/using-open-source-cedar-to-write-and-enforce-custom-authorization-policies/) — AWS Open Source Blog, 2023.
- [Two new open-source Rust crates create easier Cedar policy management](https://aws.amazon.com/blogs/opensource/easier-cedar-policy-management/) — AWS Open Source Blog, 2023.

### Modeling and comparisons

- [Cedar vs. Rego/OPA](https://www.permit.io/blog/opa-vs-cedar) — Permit.io.
- [Implementing RBAC with Cedar](https://www.permit.io/blog/cedar-rbac) — Permit.io.
- [Scaling authorization with Cedar and OPAL](https://www.permit.io/blog/scaling-authorization-with-cedar-and-opal) — Permit.io.
- [Simplifying just-in-time access governance using Cedar](https://www.commonfate.io/blog/jit-using-cedar) — Common Fate.
- [Cedarland](https://cedarland.blog/) — Independent Cedar-focused blog; verify individual post dates.

## 9. Talks and videos

- [The Cedar language and policy-based authorization with Emina Torlak](https://authorizationinsoftware.auth0.com/public/49/Authorization-in-Software-f9b69587/55f50479).
- [Use policies to manage permissions with Amazon Verified Permissions](https://www.youtube.com/watch?v=k6pPcnLuOXY) — AWS re:Invent 2022.
- [Demo of the Cedar policy language](https://www.youtube.com/watch?v=PzmDYyyA5xM).
- [AWS On Air: open-source security and Cedar](https://www.youtube.com/watch?v=T8X7VDmJkz4).
- [Fine-grained consent authorization with Cedar](https://www.youtube.com/watch?v=HnnlGBNur2w) — Identiverse 2023.

## 10. Quiet or legacy projects

These projects may still be useful, but their maintenance recency warrants extra evaluation before new adoption.

| Project | Why it is here | Last updated | Activity |
| --- | --- | ---: | :---: |
| [Joffref/cedar](https://github.com/Joffref/cedar) | Superseded for most Go users by the active official native Go implementation | 2023-11-17 | 🔴 |
| [cedargo](https://github.com/iann0036/cedargo) | Older CGO-based Go binding; official native Go implementation is active | 2024-03-12 | 🔴 |
| [Tree-sitter grammar](https://github.com/chrnorm/tree-sitter-cedar) | Useful editor grammar, but no recent repository activity | 2024-07-03 | 🔴 |
| [Zed extension](https://github.com/chrnorm/zed-cedar) | Useful editor integration, but no recent repository activity | 2024-05-13 | 🔴 |
| [Vim plugin](https://github.com/Dzordzu/vim-cedar) | Useful editor integration, but no recent repository activity | 2023-09-22 | 🔴 |

## 11. Contribution and maintenance guidance

To keep this list useful:

1. Put a resource under the job it helps a reader perform, not merely under “tools.”
2. Distinguish official Cedar projects, community open-source projects, and commercial services.
3. Include a one-line description, repository or canonical URL, last-update date, and mechanical activity label.
4. Move inactive software to **Quiet or legacy projects** instead of deleting it without explanation.
5. Do not assign activity labels to articles, videos, or product pages; show publication dates where available.
6. Recheck repository dates at least quarterly and revise the **Status checked** date.
7. Treat inclusion as discovery, not endorsement.

## License and endorsement

Unless a linked resource says otherwise, its own license and terms apply. The Cedar project and Amazon do not necessarily endorse or support community projects listed here. Evaluate third-party software before production use.
