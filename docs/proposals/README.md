# Proposals

Designs that are **not** current architecture.

The distinction matters. A proposal stored next to real schemas reads as
authoritative to anyone who finds it there — which is exactly what happened with
`schemas/component.schema.json`: it declared the pre-federation component shape
(`id`, `kind`, `status`) long after the registry had moved to the federated one
(`plane`, `architecture_status`, `owns`, `not_here`, `relationships`), had no
reader, and was contradicted by every entry in `registry/components.yaml`.

So:

* **`schemas/`** holds schemas that are enforced by something. If nothing reads
  it, it does not belong there.
* **`docs/proposals/`** holds designs that are not built. Each file says so in
  its own header, because the file will be found without this README.
* **`registry/`** holds canonical facts. A proposal becomes real when it becomes
  a registry entry or a contract in `registry/interfaces.yaml`.
