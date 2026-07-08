# .NET conventions (pinned)

C# / .NET 6+. Only my divergences from defaults — everything else, standard knowledge applies.

## Core layer naming: **ask**

`MyApp.Domain` (explicit DDD, Full tier default) vs `MyApp.Core` (community convention, Simple/Modular default). Ask; apply the tier default if I defer.

## Project layout

| Project | Purpose |
|---|---|
| `MyApp.Domain` / `MyApp.Core` | Entities, value objects, interfaces, domain services |
| `MyApp.Application` | Use cases, DTOs, commands/queries — **Full tier only** |
| `MyApp.Infrastructure` | EF Core, external APIs, file I/O implementations |
| `MyApp.WebApi` / `MyApp.Api` | Controllers or minimal API; composition root lives here |
| `MyApp.Shared` (optional) | Cross-cutting: exceptions, constants, extensions |

## Reference rules (the Dependency Rule, mechanically)

- `Domain` → references **nothing** (no ProjectReference, no infrastructure packages)
- `Application` → `Domain` only
- `Infrastructure` → `Domain` + `Application` (+ EF Core etc.)
- `WebApi` → `Application` + `Infrastructure` (host = composition root)

A violation of these `.csproj` rules **is** a dependency-rule violation — critical severity.
