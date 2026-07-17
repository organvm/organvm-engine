# Engine receipt custody

Engine receipt references resolve without a catalog:

`receipt:engine:<key>` maps to `receipts/engine/<key>.json`.

Each file is the exact public-safe owner receipt consumed by downstream
authority. The filename is identity; the RFC 8785 content digest is the
immutable binding. Receipt bodies must contain no source bodies, prompt text,
credentials, local paths, or private custody locations.

The Governance Organ ratification binds
`receipt:engine:candidate-testament-governance-native-20260716`. Its tracked
receipt digest is
`sha256:36ec614c71412b666fa4a7161c3c71cdaa04f72c6d73736dc0166c961120a2e0`;
it was generated at Engine revision
`3221208484ed0a26de88c1c434de7070b5baf78c`.
