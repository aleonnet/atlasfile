# Template `_PROJECT_PROFILE.md`

Use este template em cada projeto.

```yaml
project_id: example_project
project_label: "Example Project"
project_root: "/abs/path/to/project"
inbox_path: "_INBOX_DROP"
triage_path: "_TRIAGE_REVIEW/pending"
work_root: "_WORK"

work_areas:
  - key: juridico
    jd_number: 3
    aliases: ["juridico", "contrato", "parecer"]
  - key: financeiro
    jd_number: 2
    aliases: ["financeiro", "fiscal", "contabil"]

routing_rules:
  - when_path_contains: ["output/"]
    route_to: "entregaveis"
    confidence: 0.98
  - when_filename_contains: ["contrato", "fornecedor"]
    route_to: "juridico"
    confidence: 0.9

confidence_thresholds:
  auto_route_min: 0.85
  triage_min: 0.5
```

Notas:

- Se `path` nao for informado, o motor gera pasta no formato JD: `NN_<area_key>`.
- Se `jd_number` for informado, o numero e respeitado.
- Se `jd_number` nao for informado, o motor usa o proximo numero disponivel dinamicamente.
